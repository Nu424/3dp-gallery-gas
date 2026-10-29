// GAS のサービスを Node のメモリ上で真似る偽物と、Code.gs の読み込み。
// 実物と同じメソッド名・戻り値の形だけを用意する（Code.gs が使う範囲のみ）。
'use strict';

const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const crypto = require('node:crypto');

const CODE_PATH = path.join(__dirname, '..', '..', 'tools', 'gas', 'Code.gs');

function iterator(items) {
  let i = 0;
  return { hasNext: () => i < items.length, next: () => items[i++] };
}

// ---------------------------------------------------------------------------
// Drive
// ---------------------------------------------------------------------------
class FakeDrive {
  constructor() {
    this.nodes = new Map(); // id -> node
    this.seq = 0;
    this.blobReads = []; // getBlob() されたファイル名（meta.json を読んだか調べる用）
    this.clock = Date.UTC(2026, 0, 1);
  }
  newId(prefix) { return prefix + String(++this.seq).padStart(4, '0'); }
  addFolder(name, parentId) {
    const id = this.newId('fo');
    this.nodes.set(id, { kind: 'folder', id, name, parents: parentId ? [parentId] : [], trashed: false });
    return id;
  }
  addFile(parentId, name, content = '', opts = {}) {
    const id = this.newId('fi');
    this.clock += 1000;
    this.nodes.set(id, {
      kind: 'file', id, name, parents: [parentId], trashed: false,
      content,
      mimeType: opts.mimeType || guessMime(name),
      size: opts.size !== undefined ? opts.size : Buffer.byteLength(content, 'utf8'),
      updated: opts.updated !== undefined ? opts.updated : this.clock,
    });
    return id;
  }
  rename(id, name) { this.nodes.get(id).name = name; }
  trash(id) { this.nodes.get(id).trashed = true; }
  remove(id) { this.nodes.delete(id); }
  setContent(id, content) {
    const n = this.nodes.get(id);
    n.content = content;
    n.size = Buffer.byteLength(content, 'utf8');
    this.clock += 1000;
    n.updated = this.clock;
  }
  children(parentId, kind) {
    return [...this.nodes.values()].filter((n) => n.kind === kind && n.parents.includes(parentId));
  }
  wrap(node) {
    const drive = this;
    if (node.kind === 'folder') {
      return {
        getId: () => node.id,
        getName: () => node.name,
        isTrashed: () => node.trashed,
        // 実物の DriveApp がゴミ箱内を返すかは不確かなので、偽物はわざと返す
        getFolders: () => iterator(drive.children(node.id, 'folder').map((n) => drive.wrap(n))),
        getFiles: () => iterator(drive.children(node.id, 'file').map((n) => drive.wrap(n))),
        getParents: () => iterator(node.parents.filter((p) => drive.nodes.has(p)).map((p) => drive.wrap(drive.nodes.get(p)))),
      };
    }
    return {
      getId: () => node.id,
      getName: () => node.name,
      isTrashed: () => node.trashed,
      getMimeType: () => node.mimeType,
      getSize: () => node.size,
      getLastUpdated: () => new Date(node.updated),
      getBlob: () => ({
        getDataAsString: () => { drive.blobReads.push(node.name); return node.content; },
      }),
    };
  }
  api() {
    return {
      getFolderById: (id) => {
        const n = this.nodes.get(id);
        if (!n || n.kind !== 'folder') {
          throw new Error('No item with the given ID could be found, or you do not have permission to access it.');
        }
        return this.wrap(n);
      },
    };
  }
}

function guessMime(name) {
  const ext = (/\.([^.]+)$/.exec(name) || [])[1];
  return ({ png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', json: 'application/json',
    stl: 'model/stl', pdf: 'application/pdf' })[ext && ext.toLowerCase()] || 'application/octet-stream';
}

// ---------------------------------------------------------------------------
// Spreadsheet
// ---------------------------------------------------------------------------
class FakeSheet {
  constructor(name, gid) {
    this.name = name;
    this.gid = gid;
    this.cells = []; // 2次元配列（行・列とも0始まり）
    this.notes = {};
    this.protections = [];
    this.frozenRows = 0;
    this.failWrites = false; // true で書き込み時に権限エラーを投げる
  }
  getName() { return this.name; }
  getSheetId() { return this.gid; }
  getLastRow() {
    for (let r = this.cells.length - 1; r >= 0; r--) {
      if ((this.cells[r] || []).some((v) => v !== '' && v !== undefined && v !== null)) return r + 1;
    }
    return 0;
  }
  getRange(row, col, numRows = 1, numCols = 1) {
    if (row < 1 || col < 1 || numRows < 1 || numCols < 1) throw new Error('範囲が不正: ' + [row, col, numRows, numCols]);
    const sheet = this;
    const range = {
      getValues() {
        const out = [];
        for (let r = 0; r < numRows; r++) {
          const line = [];
          for (let c = 0; c < numCols; c++) {
            const v = (sheet.cells[row - 1 + r] || [])[col - 1 + c];
            line.push(v === undefined ? '' : v);
          }
          out.push(line);
        }
        return out;
      },
      setValues(values) {
        sheet.checkWrite();
        if (values.length !== numRows || values.some((l) => l.length !== numCols)) {
          throw new Error('The number of rows/columns in the data does not match the range.');
        }
        values.forEach((line, r) => {
          sheet.cells[row - 1 + r] = sheet.cells[row - 1 + r] || [];
          line.forEach((v, c) => { sheet.cells[row - 1 + r][col - 1 + c] = v; });
        });
        return range;
      },
      clearContent() {
        sheet.checkWrite();
        for (let r = 0; r < numRows; r++) {
          const line = sheet.cells[row - 1 + r];
          if (line) for (let c = 0; c < numCols; c++) line[col - 1 + c] = '';
        }
        return range;
      },
      setNumberFormat() { return range; },
      setFontWeight() { return range; },
      setNote(note) {
        for (let c = 0; c < numCols; c++) sheet.notes[`${row},${col + c}`] = note;
        return range;
      },
    };
    return range;
  }
  checkWrite() {
    if (this.failWrites) throw new Error('You do not have permission to edit this range.');
  }
  setFrozenRows(n) { this.frozenRows = n; }
  protect() {
    const p = { description: '', warningOnly: false };
    const api = {
      setDescription(d) { p.description = d; return api; },
      setWarningOnly(w) { p.warningOnly = w; return api; },
      _state: p,
    };
    this.protections.push(api);
    return api;
  }
  getProtections() { return this.protections.slice(); }
  // テスト用：データ行をオブジェクトで返す
  dataRows(headers) {
    const last = this.getLastRow();
    const rows = [];
    for (let r = 1; r < last; r++) {
      const line = this.cells[r] || [];
      const o = {};
      headers.forEach((h, i) => { o[h] = line[i] === undefined ? '' : line[i]; });
      if (o.folder_id) rows.push(o);
    }
    return rows;
  }
}

class FakeSpreadsheet {
  constructor() {
    this.sheets = [];
    this.toasts = [];
  }
  getSheetByName(name) { return this.sheets.find((s) => s.name === name) || null; }
  insertSheet(name) {
    const s = new FakeSheet(name, 1000 + this.sheets.length);
    this.sheets.push(s);
    return s;
  }
  getUrl() { return 'https://docs.google.com/spreadsheets/d/SSID/edit'; }
  toast(msg) { this.toasts.push(msg); }
}

// ---------------------------------------------------------------------------
// 残りのサービス
// ---------------------------------------------------------------------------
function makeProperties(initial = {}) {
  const store = { ...initial };
  return {
    store,
    api: {
      getScriptProperties: () => ({
        getProperty: (k) => (k in store ? store[k] : null),
        setProperty: (k, v) => { store[k] = String(v); },
        deleteProperty: (k) => { delete store[k]; },
      }),
    },
  };
}

function makeLock() {
  const state = { held: false, busyByOther: false, released: 0 };
  return {
    state,
    api: {
      getScriptLock: () => ({
        tryLock: () => {
          if (state.busyByOther || state.held) return false;
          state.held = true;
          return true;
        },
        releaseLock: () => { state.held = false; state.released++; },
      }),
    },
  };
}

function makeScriptApp() {
  const triggers = [];
  let seq = 0;
  const api = {
    getProjectTriggers: () => triggers.slice(),
    deleteTrigger: (t) => {
      const i = triggers.indexOf(t);
      if (i >= 0) triggers.splice(i, 1);
    },
    newTrigger: (handler) => {
      const spec = { handler };
      const builder = {
        timeBased: () => builder,
        after: (ms) => { spec.after = ms; return builder; },
        everyDays: (n) => { spec.everyDays = n; return builder; },
        atHour: (h) => { spec.atHour = h; return builder; },
        create: () => {
          const t = { spec, getHandlerFunction: () => handler, getUniqueId: () => 't' + (++seq) };
          triggers.push(t);
          return t;
        },
      };
      return builder;
    },
  };
  return { triggers, api };
}

const Utilities = {
  DigestAlgorithm: { SHA_256: 'SHA_256' },
  Charset: { UTF_8: 'UTF_8' },
  computeDigest(alg, value) {
    if (alg !== 'SHA_256') throw new Error('unsupported');
    const buf = crypto.createHash('sha256').update(String(value), 'utf8').digest();
    return [...buf].map((b) => (b > 127 ? b - 256 : b)); // GAS と同じく -128〜127
  },
  formatDate(date, tz, fmt) {
    // テストでは JST 固定の簡易版
    const d = new Date(date.getTime() + 9 * 3600 * 1000);
    const iso = d.toISOString();
    if (fmt === 'yyyy-MM-dd') return iso.slice(0, 10);
    return iso.slice(0, 19) + '+09:00';
  },
};

function makeHtmlService() {
  const calls = [];
  return {
    calls,
    api: {
      createTemplateFromFile: (name) => {
        calls.push(['template', name]);
        return {
          evaluate: () => {
            const out = {
              title: null, metas: {},
              setTitle(t) { out.title = t; return out; },
              addMetaTag(n, c) { out.metas[n] = c; return out; },
            };
            return out;
          },
        };
      },
      createHtmlOutputFromFile: (name) => ({ getContent: () => `<!-- ${name} -->` }),
    },
  };
}

/**
 * 偽物一式を用意して Code.gs を読み込む。
 * @return {{ctx, drive, ss, props, lock, script, html, itemsId}}
 */
function setupEnv({ withItemsFolder = true, props: initialProps } = {}) {
  const drive = new FakeDrive();
  const root = drive.addFolder('3Dギャラリー', null);
  const itemsId = withItemsFolder ? drive.addFolder('items', root) : null;
  const ss = new FakeSpreadsheet();
  const props = makeProperties(initialProps || (itemsId ? { ITEMS_FOLDER_ID: itemsId } : {}));
  const lock = makeLock();
  const script = makeScriptApp();
  const html = makeHtmlService();
  const logs = [];

  const sandbox = {
    DriveApp: drive.api(),
    SpreadsheetApp: {
      getActiveSpreadsheet: () => ss,
      ProtectionType: { SHEET: 'SHEET', RANGE: 'RANGE' },
      getUi: () => { throw new Error('getUi はテストでは使わない'); },
    },
    PropertiesService: props.api,
    LockService: lock.api,
    ScriptApp: script.api,
    HtmlService: html.api,
    Utilities,
    Session: { getScriptTimeZone: () => 'Asia/Tokyo' },
    Logger: { log: (m) => logs.push(m) },
    console,
  };
  const ctx = vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(CODE_PATH, 'utf8'), ctx, { filename: 'Code.gs' });
  return { ctx, drive, ss, props, lock, script, html, itemsId, logs };
}

/** vm の中で作られたオブジェクトを、テスト側の普通のオブジェクトにする（deepStrictEqual 用） */
function plain(v) {
  return v === undefined ? v : JSON.parse(JSON.stringify(v));
}

module.exports = { setupEnv, plain, FakeDrive };
