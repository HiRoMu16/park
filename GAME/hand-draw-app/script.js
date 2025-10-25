// hand-draw-app/script.js

const video = document.getElementById("video");
const landmarkCanvas = document.getElementById("landmark-canvas");
const landmarkCtx = landmarkCanvas.getContext("2d");
const drawCanvas = document.getElementById("draw-canvas");
const drawCtx = drawCanvas.getContext("2d");

function resizeCanvas() {
  const width = window.innerWidth;
  const height = window.innerHeight;
  [landmarkCanvas, drawCanvas].forEach(canvas => {
    canvas.width = width;
    canvas.height = height;
  });
}
resizeCanvas();
window.addEventListener("resize", resizeCanvas);

let paths = [];
let currentPath = [];
const INDEX_FINGER_TIP = 8;
let openHandStartTime = null;
const REQUIRED_HOLD_TIME_MS = 5000;

const hands = new Hands({
  locateFile: (file) => `https://cdn.jsdelivr.net/npm/@mediapipe/hands/${file}`
});
hands.setOptions({
  maxNumHands: 2,
  modelComplexity: 1,
  minDetectionConfidence: 0.8,
  minTrackingConfidence: 0.5
});
hands.onResults(onResults);

function mirrorX(x) {
  return drawCanvas.width - x;
}

function onResults(results) {
  landmarkCtx.save();
  landmarkCtx.clearRect(0, 0, landmarkCanvas.width, landmarkCanvas.height);
  landmarkCtx.scale(-1, 1);
  landmarkCtx.translate(-landmarkCanvas.width, 0);

  if (results.multiHandLandmarks && results.multiHandedness) {
    results.multiHandLandmarks.forEach((landmarks, i) => {
      drawConnectors(landmarkCtx, landmarks, HAND_CONNECTIONS, { color: "#00FF00", lineWidth: 2 });
      drawLandmarks(landmarkCtx, landmarks, { color: "#FF0000", lineWidth: 1 });
    });

    landmarkCtx.restore();

    let leftHand = null;
    let rightHand = null;
    results.multiHandedness.forEach((handed, i) => {
      if (handed.label === "Left") leftHand = results.multiHandLandmarks[i];
      if (handed.label === "Right") rightHand = results.multiHandLandmarks[i];
    });

    const leftOpen = leftHand ? isHandOpen(leftHand) : false;
    const rightOpen = rightHand ? isHandOpen(rightHand) : false;

    // ?? 左手で "パー" のときだけ描画
    if (leftHand && leftOpen) {
      const finger = leftHand[INDEX_FINGER_TIP];
      const x = mirrorX(finger.x * drawCanvas.width);
      const y = finger.y * drawCanvas.height;
      currentPath.push({ x, y });
      paths.push([...currentPath]);
    } else {
      currentPath = [];
    }

    // ? 右手で "パー" を5秒間続けたら全消去
    if (rightHand && rightOpen) {
      if (!openHandStartTime) {
        openHandStartTime = performance.now();
      } else {
        const duration = performance.now() - openHandStartTime;
        if (duration >= REQUIRED_HOLD_TIME_MS) {
          clearCanvas();
          openHandStartTime = null;
        }
      }
    } else {
      openHandStartTime = null;
    }
  } else {
    landmarkCtx.restore();
  }

  redrawPaths();
}

function redrawPaths() {
  drawCtx.clearRect(0, 0, drawCanvas.width, drawCanvas.height);
  drawCtx.strokeStyle = "black";
  drawCtx.lineWidth = 4;
  drawCtx.lineCap = "round";
  for (const path of paths) {
    if (path.length < 2) continue;
    drawCtx.beginPath();
    drawCtx.moveTo(path[0].x, path[0].y);
    for (let i = 1; i < path.length; i++) {
      drawCtx.lineTo(path[i].x, path[i].y);
    }
    drawCtx.stroke();
  }
}

function clearCanvas() {
  paths = [];
  currentPath = [];
  drawCtx.clearRect(0, 0, drawCanvas.width, drawCanvas.height);
  console.log("? キャンバス全消去！");
}

function isHandOpen(landmarks) {
  const fingers = [8, 12, 16, 20];
  const bases = [5, 9, 13, 17];
  let extendedCount = 0;
  for (let i = 0; i < fingers.length; i++) {
    const tip = landmarks[fingers[i]];
    const base = landmarks[bases[i]];
    const dist = Math.hypot(tip.x - base.x, tip.y - base.y);
    if (dist > 0.1) extendedCount++;
  }
  return extendedCount >= 4;
}

const camera = new Camera(video, {
  onFrame: async () => {
    await hands.send({ image: video });
  },
  width: 640,
  height: 480,
});
camera.start();
