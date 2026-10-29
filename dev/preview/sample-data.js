// プレビュー用のサンプルデータ（getGalleryData() の戻り値と同じ形）。
// モック（docs/gallery_mock.html）のサンプル8件＋要対応1件を移したもの。
// thumbUrl は、表示できる画像（data: のSVG）／実在しないURL（読み込み失敗でアイコンに替わる確認用）／null を混ぜている。

// data: のSVG画像（表示できるサムネイルの代わり）
const svgThumb = (bg, fg, label) => 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(
  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 180"><rect width="240" height="180" fill="${bg}"/>` +
  `<circle cx="120" cy="82" r="46" fill="${fg}" fill-opacity=".85"/><rect x="60" y="130" width="120" height="14" rx="7" fill="${fg}" fill-opacity=".5"/>` +
  `<text x="120" y="92" text-anchor="middle" font-size="30" font-family="sans-serif" fill="#fff">${label}</text></svg>`);

// 実在しないURL（読み込み失敗→形のアイコン）
const broken = (id) => `https://drive.google.com/thumbnail?id=preview-not-exist-${id}&sz=w600`;

const files = (id, names) => names.map((n) => ({
  name: n,
  url: `https://example.com/preview/${id}/${encodeURIComponent(n)}/view`,
  downloadUrl: `https://example.com/preview/${id}/${encodeURIComponent(n)}/download`
}));
// 写真：thumb を渡すと表示できる画像、null なら実在しないURL（失敗→写真アイコン）
const photos = (id, thumb, names) => names.map((n) => ({ name: n, url: thumb ? thumb(n) : broken(id + '-' + n) }));

export const SAMPLE_DATA = {
  syncedAt: '2026-10-29T09:12:00+09:00',
  sheetUrl: 'https://example.com/preview/sheet',
  statuses: ['使用中', '参考', '引退'],
  canSync: true,
  items: [
    { folderId: 'id-tray-0210', folderName: '20260210_恒温槽用トレイ', folderUrl: 'https://example.com/preview/folder/tray', date: '2026-02-10', name: '恒温槽用トレイ', author: '鈴木', purpose: '恒温槽の中でサンプル瓶6本を立てておく', status: '使用中',
      tags: ['恒温槽', '収納'], note: ['PETGで印刷。PLAだと60℃で反る。', '瓶の径は22mm想定。'],
      thumbUrl: svgThumb('#CFE0F3', '#4F86C6', 'TRAY'), photos: photos('tray', () => svgThumb('#E3ECF7', '#4F86C6', 'photo'), ['photo_槽内.jpg']),
      files: files('tray', ['tray.f3d', 'tray.step', 'tray.stl', 'tray.3mf', 'thumb.png', 'photo_槽内.jpg']) },
    { folderId: 'id-spacer-0903', folderName: '20250903_ステージ用スペーサー', folderUrl: 'https://example.com/preview/folder/spacer', date: '2025-09-03', name: 'ステージ用スペーサー', author: '佐藤', purpose: '顕微鏡ステージの高さを3mm上げる', status: '参考',
      tags: ['顕微鏡'], note: ['旧ステージ用。新ステージでは不要。', '厚みはFusionのパラメータで変えられる。'],
      thumbUrl: null, photos: [],
      files: files('spacer', ['spacer.f3d', 'spacer.step', 'spacer.stl', 'thumb.png']) },
    { folderId: 'id-holder-0612', folderName: '20250612_流路セルホルダー', folderUrl: 'https://example.com/preview/folder/holder', date: '2025-06-12', name: '流路セルホルダー', author: '山田', purpose: '流路セルを顕微鏡ステージに固定する', status: '使用中',
      tags: ['顕微鏡', '治具'], note: ['M3ネジ×4で固定。', '縦向きで刷らないと爪が折れる。', 'v2で穴径を0.2mm拡大。'],
      thumbUrl: broken('holder'), photos: photos('holder', null, ['photo_使用中.jpg', 'photo_裏側.jpg']),
      files: files('holder', ['holder.f3d', 'holder.step', 'base.stl', 'clip.stl', 'holder.3mf', 'thumb.png', 'photo_使用中.jpg', 'photo_裏側.jpg']) },
    { folderId: 'id-pipette-1118', folderName: '20241118_ピペットスタンド', folderUrl: 'https://example.com/preview/folder/pipette', date: '2024-11-18', name: 'ピペットスタンド', author: '鈴木', purpose: '8連ピペットを立てて置く', status: '使用中',
      tags: ['実験台', '収納'], note: ['底に滑り止めシールを貼っている。'],
      thumbUrl: svgThumb('#D5EBDA', '#5B9E6A', 'STAND'), photos: photos('pipette', () => svgThumb('#E6F2E9', '#5B9E6A', 'photo'), ['photo_実験台.jpg']),
      files: files('pipette', ['stand.f3d', 'stand.step', 'stand.stl', 'thumb.png', 'photo_実験台.jpg']) },
    { folderId: 'id-camera-0405', folderName: '20240405_カメラマウント', folderUrl: 'https://example.com/preview/folder/camera', date: '2024-04-05', name: 'カメラマウント', author: '山田', purpose: 'USBカメラを光学定盤に取り付ける', status: '使用中',
      tags: ['カメラ', '光学'], note: ['M6ネジで定盤に固定。', 'カメラ側は1/4インチネジ。'],
      thumbUrl: broken('camera'), photos: photos('camera', null, ['photo_取付.jpg']),
      files: files('camera', ['mount.f3d', 'mount.step', 'mount.stl', 'mount.3mf', 'thumb.png', 'photo_取付.jpg']) },
    { folderId: 'id-clamp-1020', folderName: '20231020_チューブクランプ', folderUrl: 'https://example.com/preview/folder/clamp', date: '2023-10-20', name: 'チューブクランプ', author: '田中', purpose: 'シリコンチューブを挟んで流量を絞る', status: '引退',
      tags: ['流路'], note: ['ポンプ更新で不要になった。', 'ヒンジ部は0.4mmのすき間で一体印刷。'],
      thumbUrl: null, photos: [],
      files: files('clamp', ['clamp.f3d', 'clamp.step', 'clamp.stl', 'thumb.png']) },
    { folderId: 'id-fiber-0615', folderName: '20230615_光ファイバーホルダー', folderUrl: 'https://example.com/preview/folder/fiber', date: '2023-06-15', name: '光ファイバーホルダー', author: '佐藤', purpose: 'ファイバー端を試料に向けて保持する', status: '参考',
      tags: ['光学'], note: ['角度違いで3種類ある。'],
      thumbUrl: svgThumb('#F2D5D4', '#D9534F', 'FIBER'), photos: [],
      files: files('fiber', ['fiber.f3d', 'fiber.step', 'fiber_30deg.stl', 'fiber_45deg.stl', 'fiber_60deg.stl', 'thumb.png']) },
    { folderId: 'id-cable-0930', folderName: '20220930_ケーブルガイド', folderUrl: 'https://example.com/preview/folder/cable', date: '2022-09-30', name: 'ケーブルガイド', author: '田中', purpose: '装置背面のケーブルを束ねて這わせる', status: '使用中',
      tags: ['配線'], note: ['元のf3dは残っていない。直すなら作り直し。'],
      thumbUrl: null, photos: [],
      files: files('cable', ['guide.stl', 'thumb.jpg']) }
  ],
  issues: [
    { folderId: 'id-fanduct-0722', folderName: '20260722_ファンダクト試作', problem: 'meta.json の purpose が空です',
      url: 'https://example.com/preview/folder/fanduct', rowUrl: 'https://example.com/preview/sheet#gid=0&range=A9' }
  ]
};
