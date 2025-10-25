// HTML要素たち
const video = document.getElementById('video');
const canvas = document.getElementById('game-canvas');
const ctx = canvas.getContext('2d');
const scoreElement = document.getElementById('score');
const resultElement = document.getElementById('result');
const startButton = document.getElementById('start-button');

// ゲーム設定
let detector;
let poses = [];
let fruits = [];
let score = 0;
let isPlaying = false;
let gameTimer;

// 果物画像
const ripeImage = new Image();
ripeImage.src = 'assets/kaki_ripe.png';
const unripeImage = new Image();
unripeImage.src = 'assets/kaki_unripe.png';

ripeImage.onerror = () => console.error("熟した柿画像が読み込めないぞ！");
unripeImage.onerror = () => console.error("未熟な柿画像が読み込めないぞ！");

// Canvasサイズをカメラ映像に合わせる関数 ← 修正
function resizeCanvas() {
    // カメラ映像の実際のサイズを取得
    const videoWidth = video.videoWidth;
    const videoHeight = video.videoHeight;

    // カメラ映像のサイズが取得できたらCanvasの内部解像度と表示サイズを合わせる
    if (videoWidth > 0 && videoHeight > 0) {
        canvas.width = videoWidth;
        canvas.height = videoHeight;
        canvas.style.width = video.clientWidth + 'px';
        canvas.style.height = video.clientHeight + 'px';
    }
}

// カメラ起動 ← 修正
async function setupCamera() {
    const stream = await navigator.mediaDevices.getUserMedia({ video: true });
    video.srcObject = stream;

    return new Promise(resolve => {
        video.onloadedmetadata = () => {
            // 映像のメタデータが読み込まれたらCanvasのサイズを合わせる
            resizeCanvas();
            // ウィンドウサイズが変更されたときもCanvasサイズを追従させる
            window.addEventListener('resize', resizeCanvas);
            resolve(video);
        };
    });
}

// MoveNetセットアップ
async function setupMoveNet() {
    detector = await poseDetection.createDetector(poseDetection.SupportedModels.MoveNet, {
        modelType: poseDetection.movenet.modelType.SINGLEPOSE_LIGHTNING
    });
}

// キーポイントから座標取得
function getLandmark(keyName) {
    const kp = poses[0]?.keypoints.find(p => p.name === keyName);
    // 認識の信頼度が30%以上のキーポイントのみを有効とする
    return (kp && kp.score > 0.3) ? kp : null;
}

// ゲームループ ← 修正
async function gameLoop() {
    if (!isPlaying) return;

    // 姿勢を推定
    poses = await detector.estimatePoses(video);

    // Canvasをクリア
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // 骨格を描画（左右反転対応）
    drawPose();

    // 果物を更新して描画
    updateAndDrawFruits();

    // 衝突判定を実行
    detectCollisions();

    // 次のフレームを要求
    requestAnimationFrame(gameLoop);
}

// 骨格の描画（左右反転対応） ← 修正
function drawPose() {
    if (!poses[0]) return;

    // 描画設定を一旦保存
    ctx.save();
    // Canvasの描画コンテキストを左右反転させる
    ctx.scale(-1, 1);
    ctx.translate(-canvas.width, 0);

    const keypoints = poses[0].keypoints;

    // キーポイント（関節）を描画
    keypoints.forEach(kp => {
        if (kp.score > 0.3) {
            ctx.beginPath();
            ctx.arc(kp.x, kp.y, 5, 0, Math.PI * 2);
            ctx.fillStyle = "aqua";
            ctx.fill();
        }
    });

    // 骨組み（線）を描画
    const adjacentPairs = poseDetection.util.getAdjacentPairs(poseDetection.SupportedModels.MoveNet);
    adjacentPairs.forEach(([i, j]) => {
        const kp1 = keypoints[i];
        const kp2 = keypoints[j];

        if (kp1.score > 0.3 && kp2.score > 0.3) {
            ctx.beginPath();
            ctx.moveTo(kp1.x, kp1.y);
            ctx.lineTo(kp2.x, kp2.y);
            ctx.strokeStyle = "lime";
            ctx.lineWidth = 2;
            ctx.stroke();
        }
    });

    // 保存した描画設定に戻す（これ以降の描画が反転しないようにするため）
    ctx.restore();
}

// 果物の生成
function spawnFruit() {
    const isRipe = Math.random() < 0.5;
    fruits.push({
        x: Math.random() * canvas.clientWidth, // ← Canvasの表示幅に合わせる
        y: -150,
        speed: 1.5 + Math.random() * 2,
        isRipe
    });
}

// 衝突判定のロジック ← 修正
function isHit(point, fruit) {
    if (!point) return false;

    // 骨格は反転描画しているため、当たり判定に使うキーポイントのX座標も反転させて計算する
    const mirroredPointX = canvas.width - point.x;
    const dx = mirroredPointX - fruit.x;
    const dy = point.y - fruit.y;
    const distance = Math.sqrt(dx * dx + dy * dy);

    // 果物の半径（約50px）より距離が近ければ衝突とみなす
    return distance < 50;
}

// 果物の更新と描画をまとめて行う関数 ← 追加
function updateAndDrawFruits() {
    fruits.forEach(fruit => {
        // 果物を下に移動
        fruit.y += fruit.speed;

        // 果物の画像を描画（画像の中心が座標になるように調整）
        const img = fruit.isRipe ? ripeImage : unripeImage;
        ctx.drawImage(img, fruit.x - 50, fruit.y - 50, 100, 100);
    });

    // 画面外に出た果物を配列から削除
    fruits = fruits.filter(fruit => fruit.y < canvas.height + 50);
}


// 衝突判定とスコア処理
function detectCollisions() {
    const nose = getLandmark("nose");
    const leftHand = getLandmark("left_wrist");
    const rightHand = getLandmark("right_wrist");

    const fruitsToRemove = [];

    fruits.forEach(fruit => {
        let hit = false;
        // 頭（鼻）に当たった場合
        if (isHit(nose, fruit)) {
            score += fruit.isRipe ? 10 : -5; // 熟した柿: +10点, 未熟な柿: -5点
            hit = true;
        }
        // 手（手首）に当たった場合
        else if (isHit(leftHand, fruit) || isHit(rightHand, fruit)) {
            score += fruit.isRipe ? -5 : 10; // 熟した柿: -5点, 未熟な柿: +10点
            hit = true;
        }

        if (hit) {
            fruitsToRemove.push(fruit);
        }
    });

    // 衝突した果物を配列から削除
    fruits = fruits.filter(fruit => !fruitsToRemove.includes(fruit));

    // スコアを更新
    scoreElement.textContent = `スコア: ${score}`;
}

// スタート処理
async function startGame() {
    startButton.style.display = 'none';
    resultElement.style.display = 'none';
    score = 0;
    fruits = [];
    isPlaying = true;
    scoreElement.textContent = `スコア: ${score}`; // ← 追加：スコア表示をリセット

    await setupCamera();
    await setupMoveNet();

    gameLoop();
    gameTimer = setInterval(spawnFruit, 800); // 果物落下間隔
    setTimeout(endGame, 30000); // 30秒で終了
}

// 終了処理
function endGame() {
    isPlaying = false;
    clearInterval(gameTimer);
    video.srcObject.getTracks().forEach(track => track.stop()); // ← 追加: カメラを停止
    resultElement.textContent = `あなたのスコアは ${score} 点です！`;
    resultElement.style.display = 'block';
    startButton.style.display = 'inline-block';
}

// イベント
startButton.addEventListener('click', startGame);

// const video = document.getElementById('video');
// const canvas = document.getElementById('game-canvas');
// const ctx = canvas.getContext('2d');
// const scoreElement = document.getElementById('score');
// const resultElement = document.getElementById('result');
// const startButton = document.getElementById('start-button');

// const visibleParts = [
//   "nose", "left_eye", "right_eye",
//   "left_wrist", "right_wrist",
//   "left_shoulder", "right_shoulder"
// ];

// let detector;
// let poses = [];
// let fruits = [];
// let score = 0;
// let isPlaying = false;
// let gameTimer;
// let hitEffects = [];

// const ripeImage = new Image();
// ripeImage.src = 'assets/kaki_ripe.png';
// const unripeImage = new Image();
// unripeImage.src = 'assets/kaki_unripe.png';

// function resizeCanvas() {
//   canvas.width = window.innerWidth;
//   canvas.height = window.innerHeight;
//   canvas.style.width = window.innerWidth + 'px';
//   canvas.style.height = window.innerHeight + 'px';
// }
// resizeCanvas();
// window.addEventListener('resize', resizeCanvas);

// async function setupCamera() {
//   const stream = await navigator.mediaDevices.getUserMedia({ video: true });
//   video.srcObject = stream;
//   return new Promise(resolve => {
//     video.onloadedmetadata = () => resolve(video);
//   });
// }

// async function setupMoveNet() {
//   detector = await poseDetection.createDetector(poseDetection.SupportedModels.MoveNet, {
//     modelType: poseDetection.movenet.modelType.SINGLEPOSE_LIGHTNING
//   });
// }

// function getLandmark(name) {
//   const kp = poses[0]?.keypoints.find(p => p.name === name);
//   return (kp && kp.score > 0.5) ? kp : null;
// }

// function addHitEffect(fruitX, fruitY, scoreText, color) {
//   hitEffects.push({
//     x: fruitX,
//     y: fruitY - 40,
//     text: scoreText,
//     color: color,
//     alpha: 1.0,
//     dy: -1,
//     fontSize: 64
//   });
// }

// function updateHitEffects() {
//   hitEffects.forEach(effect => {
//     effect.y += effect.dy;
//     effect.alpha -= 0.02;
//   });
//   hitEffects = hitEffects.filter(e => e.alpha > 0);
// }

// function drawHitEffects() {
//   hitEffects.forEach(effect => {
//     ctx.save();
//     ctx.globalAlpha = effect.alpha;
//     ctx.font = `bold ${effect.fontSize}px sans-serif`;
//     ctx.textAlign = "center";
//     ctx.lineWidth = 6;
//     ctx.strokeStyle = "black";
//     ctx.strokeText(effect.text, effect.x, effect.y);
//     ctx.fillStyle = effect.color;
//     ctx.fillText(effect.text, effect.x, effect.y);
//     ctx.restore();
//   });
// }

// function drawPose() {
//   if (!poses[0]) return;
//   ctx.save();
//   ctx.scale(-1, 1);
//   ctx.translate(-canvas.width, 0);

//   const keypoints = poses[0].keypoints;
//   const filteredKeypoints = keypoints.filter(
//     kp => visibleParts.includes(kp.name) && kp.score > 0.5
//   );

//   filteredKeypoints.forEach(kp => {
//     ctx.beginPath();
//     ctx.arc(kp.x, kp.y, 10, 0, Math.PI * 2);
//     ctx.fillStyle = "cyan";
//     ctx.fill();
//   });

//   const adjacentPairs = poseDetection.util.getAdjacentPairs(poseDetection.SupportedModels.MoveNet);
//   adjacentPairs.forEach(([i, j]) => {
//     const kp1 = keypoints[i];
//     const kp2 = keypoints[j];
//     if (
//       visibleParts.includes(kp1.name) &&
//       visibleParts.includes(kp2.name) &&
//       kp1.score > 0.5 &&
//       kp2.score > 0.5
//     ) {
//       ctx.beginPath();
//       ctx.moveTo(kp1.x, kp1.y);
//       ctx.lineTo(kp2.x, kp2.y);
//       ctx.strokeStyle = "lime";
//       ctx.lineWidth = 6;
//       ctx.stroke();
//     }
//   });

//   ctx.restore();
// }

// function detectCollisions() {
//   const nose = getLandmark("nose");
//   const leftHand = getLandmark("left_wrist");
//   const rightHand = getLandmark("right_wrist");

//   fruits = fruits.filter(fruit => {
//     const fx = fruit.x;
//     const fy = fruit.y;

//     if (isHit(nose, fruit)) {
//       const scoreChange = fruit.isRipe ? 10 : -5;
//       score += scoreChange;
//       addHitEffect(fx, fy, `${scoreChange > 0 ? "+" : ""}${scoreChange}`, scoreChange > 0 ? "yellow" : "red");
//       return false;
//     }
//     if (isHit(leftHand, fruit) || isHit(rightHand, fruit)) {
//       const scoreChange = fruit.isRipe ? -5 : 10;
//       score += scoreChange;
//       addHitEffect(fx, fy, `${scoreChange > 0 ? "+" : ""}${scoreChange}`, scoreChange > 0 ? "yellow" : "red");
//       return false;
//     }
//     return true;
//   });

//   scoreElement.textContent = `スコア: ${score}`;
// }

// function isHit(point, fruit) {
//   if (!point) return false;
//   const flippedX = canvas.width - point.x;
//   const dx = flippedX - fruit.x;
//   const dy = point.y - fruit.y;
//   const distance = Math.sqrt(dx * dx + dy * dy);
//   return distance < 50;
// }

// function updateFruits() {
//   ctx.clearRect(0, 0, canvas.width, canvas.height);
//   drawPose();

//   fruits.forEach(fruit => {
//     fruit.y += fruit.speed;
//     const img = fruit.isRipe ? ripeImage : unripeImage;
//     ctx.drawImage(img, fruit.x - 50, fruit.y - 50, 100, 100);
//   });

//   drawHitEffects();
//   updateHitEffects();

//   fruits = fruits.filter(fruit => fruit.y < canvas.height + 50);
// }

// async function gameLoop() {
//   if (!isPlaying) return;
//   poses = await detector.estimatePoses(video);
//   updateFruits();
//   detectCollisions();
//   requestAnimationFrame(gameLoop);
// }

// function spawnFruit() {
//   const isRipe = Math.random() < 0.5;
//   const fruit = {
//     x: Math.random() * canvas.width,
//     y: -50,
//     speed: 3 + Math.random() * 3,
//     isRipe
//   };
//   fruits.push(fruit);
// }

// async function startGame() {
//   startButton.style.display = 'none';
//   resultElement.style.display = 'none';
//   score = 0;
//   fruits = [];
//   isPlaying = true;

//   await setupCamera();
//   await setupMoveNet();

//   gameLoop();
//   gameTimer = setInterval(spawnFruit, 800);
//   setTimeout(endGame, 30000);
// }

// function endGame() {
//   isPlaying = false;
//   clearInterval(gameTimer);
//   resultElement.textContent = `あなたのスコアは ${score} 点です！`;
//   resultElement.style.display = 'block';
//   startButton.style.display = 'inline-block';
// }

// startButton.addEventListener('click', startGame);

// window.addEventListener("error", e => {
//   console.error("💥 エラー:", e.message);
// });
