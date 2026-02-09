const BOARD_SIZE = 8;
const PIECE_COUNT = 3;
const MAHJONG_PROB = 0.28;

const COLORS = ["#4fd1ff", "#ff6b6b", "#7ee081", "#f7c948", "#b38bff", "#ff9f1c"];

const SHAPES = [
  [[0, 0]],
  [[0, 0], [1, 0]],
  [[0, 0], [0, 1]],
  [[0, 0], [1, 0], [2, 0]],
  [[0, 0], [0, 1], [0, 2]],
  [[0, 0], [1, 0], [0, 1], [1, 1]],
  [[0, 0], [1, 0], [2, 0], [3, 0]],
  [[0, 0], [0, 1], [0, 2], [0, 3]],
  [[0, 0], [1, 0], [2, 0], [0, 1], [1, 1], [2, 1]],
  [[0, 0], [0, 1], [1, 1], [2, 1]],
  [[0, 0], [1, 0], [2, 0], [2, 1]],
  [[0, 0], [1, 0], [2, 0], [1, 1]],
  [[0, 0], [0, 1], [1, 1], [2, 1]],
  [[0, 0], [1, 0], [1, 1]],
  [[0, 0], [0, 1], [1, 0]],
  [[0, 0], [1, 0], [1, 1], [2, 1]],
];

const boardEl = document.getElementById("board");
const piecesEl = document.getElementById("pieces");
const statusEl = document.getElementById("status");
const mahjongBarEl = document.getElementById("mahjongBar");

let board = [];
let pieces = [];
let selectedPieceId = null;
let collected = Array(9).fill(false);
let preview = [];

const mahjongSvgs = Array.from({ length: 9 }, (_, i) => createBingSvg(i + 1));

function initBoard() {
  board = Array.from({ length: BOARD_SIZE }, () =>
    Array.from({ length: BOARD_SIZE }, () => ({ filled: false, color: "", mahjong: null }))
  );
  boardEl.innerHTML = "";
  for (let r = 0; r < BOARD_SIZE; r += 1) {
    for (let c = 0; c < BOARD_SIZE; c += 1) {
      const cell = document.createElement("div");
      cell.className = "cell";
      cell.dataset.row = String(r);
      cell.dataset.col = String(c);
      cell.addEventListener("mouseenter", onCellHover);
      cell.addEventListener("mouseleave", clearPreview);
      cell.addEventListener("click", onCellClick);
      boardEl.appendChild(cell);
    }
  }
}

function initMahjongBar() {
  mahjongBarEl.innerHTML = "";
  for (let i = 1; i <= 9; i += 1) {
    const slot = document.createElement("div");
    slot.className = "mahjong-slot";
    slot.dataset.value = String(i);
    const img = document.createElement("img");
    img.src = mahjongSvgs[i - 1];
    img.alt = `${i}饼`;
    const label = document.createElement("div");
    label.className = "label";
    label.textContent = `${i}饼`;
    slot.appendChild(img);
    slot.appendChild(label);
    mahjongBarEl.appendChild(slot);
  }
}

function generatePieces() {
  pieces = Array.from({ length: PIECE_COUNT }, () => createPiece());
  renderPieces();
}

function createPiece() {
  const shape = SHAPES[Math.floor(Math.random() * SHAPES.length)];
  const color = COLORS[Math.floor(Math.random() * COLORS.length)];
  let mahjong = null;
  if (Math.random() < MAHJONG_PROB) {
    const value = Math.floor(Math.random() * 9) + 1;
    const cellIndex = Math.floor(Math.random() * shape.length);
    mahjong = { value, index: cellIndex };
  }
  return { id: crypto.randomUUID(), shape, color, mahjong, used: false };
}

function renderPieces() {
  piecesEl.innerHTML = "";
  pieces.forEach((piece) => {
    const card = document.createElement("div");
    card.className = "piece-card";
    card.dataset.id = piece.id;
    if (piece.id === selectedPieceId) {
      card.classList.add("selected");
    }
    card.addEventListener("click", () => selectPiece(piece.id));

    const coords = piece.shape;
    const maxRow = Math.max(...coords.map((c) => c[1]));
    const maxCol = Math.max(...coords.map((c) => c[0]));
    const grid = document.createElement("div");
    grid.className = "piece-grid";
    grid.style.gridTemplateColumns = `repeat(${maxCol + 1}, 26px)`;

    coords.forEach((c, idx) => {
      const block = document.createElement("div");
      block.className = "piece-cell";
      block.style.setProperty("--piece-color", piece.color);
      if (piece.mahjong && piece.mahjong.index === idx) {
        const tile = document.createElement("div");
        tile.className = "mini-mahjong";
        const img = document.createElement("img");
        img.src = mahjongSvgs[piece.mahjong.value - 1];
        img.alt = `${piece.mahjong.value}饼`;
        tile.appendChild(img);
        block.appendChild(tile);
      }
      grid.appendChild(block);
    });

    grid.style.gridTemplateRows = `repeat(${maxRow + 1}, 26px)`;
    card.appendChild(grid);
    piecesEl.appendChild(card);
  });
}

function selectPiece(id) {
  selectedPieceId = id;
  renderPieces();
}

function onCellHover(event) {
  if (!selectedPieceId) return;
  const cell = event.currentTarget;
  const row = Number(cell.dataset.row);
  const col = Number(cell.dataset.col);
  showPreview(row, col);
}

function clearPreview() {
  preview.forEach((cell) => cell.classList.remove("preview", "invalid"));
  preview = [];
}

function showPreview(row, col) {
  clearPreview();
  const piece = pieces.find((p) => p.id === selectedPieceId);
  if (!piece) return;
  const cells = piece.shape.map(([x, y]) => ({ r: row + y, c: col + x }));
  let valid = true;
  cells.forEach(({ r, c }) => {
    if (r < 0 || c < 0 || r >= BOARD_SIZE || c >= BOARD_SIZE) valid = false;
    else if (board[r][c].filled) valid = false;
  });
  cells.forEach(({ r, c }) => {
    if (r < 0 || c < 0 || r >= BOARD_SIZE || c >= BOARD_SIZE) return;
    const target = getCellEl(r, c);
    if (target) {
      target.classList.add(valid ? "preview" : "invalid");
      preview.push(target);
    }
  });
}

function onCellClick(event) {
  if (!selectedPieceId) return;
  const cell = event.currentTarget;
  const row = Number(cell.dataset.row);
  const col = Number(cell.dataset.col);
  const piece = pieces.find((p) => p.id === selectedPieceId);
  if (!piece) return;
  const positions = piece.shape.map(([x, y]) => ({ r: row + y, c: col + x }));
  if (!canPlace(positions)) {
    statusEl.textContent = "这里放不下，换个位置试试。";
    return;
  }
  placePiece(piece, positions);
  piece.used = true;
  selectedPieceId = null;
  renderPieces();
  clearPreview();
  const cleared = clearLines();
  if (cleared > 0) {
    statusEl.textContent = `消除了 ${cleared} 行/列，继续收集饼子！`;
  } else {
    statusEl.textContent = "";
  }
  if (pieces.every((p) => p.used)) {
    generatePieces();
  }
  if (isGameOver()) {
    statusEl.textContent = "没有可放的方块了，刷新重新挑战！";
  }
}

function canPlace(positions) {
  return positions.every(({ r, c }) => r >= 0 && c >= 0 && r < BOARD_SIZE && c < BOARD_SIZE && !board[r][c].filled);
}

function placePiece(piece, positions) {
  positions.forEach((pos, idx) => {
    board[pos.r][pos.c] = {
      filled: true,
      color: piece.color,
      mahjong: piece.mahjong && piece.mahjong.index === idx ? piece.mahjong.value : null,
    };
  });
  renderBoard();
}

function renderBoard() {
  for (let r = 0; r < BOARD_SIZE; r += 1) {
    for (let c = 0; c < BOARD_SIZE; c += 1) {
      const cellEl = getCellEl(r, c);
      const cell = board[r][c];
      if (!cellEl) continue;
      cellEl.classList.toggle("filled", cell.filled);
      cellEl.style.setProperty("--piece-color", cell.color || "transparent");
      cellEl.innerHTML = "";
      if (cell.filled && cell.mahjong) {
        const tile = document.createElement("div");
        tile.className = "mahjong";
        const img = document.createElement("img");
        img.src = mahjongSvgs[cell.mahjong - 1];
        img.alt = `${cell.mahjong}饼`;
        tile.appendChild(img);
        cellEl.appendChild(tile);
      }
    }
  }
}

function clearLines() {
  const rowsToClear = [];
  const colsToClear = [];
  for (let r = 0; r < BOARD_SIZE; r += 1) {
    if (board[r].every((cell) => cell.filled)) rowsToClear.push(r);
  }
  for (let c = 0; c < BOARD_SIZE; c += 1) {
    let full = true;
    for (let r = 0; r < BOARD_SIZE; r += 1) {
      if (!board[r][c].filled) {
        full = false;
        break;
      }
    }
    if (full) colsToClear.push(c);
  }

  if (rowsToClear.length === 0 && colsToClear.length === 0) return 0;

  const clearedCells = new Set();
  rowsToClear.forEach((r) => {
    for (let c = 0; c < BOARD_SIZE; c += 1) {
      clearedCells.add(`${r}-${c}`);
    }
  });
  colsToClear.forEach((c) => {
    for (let r = 0; r < BOARD_SIZE; r += 1) {
      clearedCells.add(`${r}-${c}`);
    }
  });

  clearedCells.forEach((key) => {
    const [r, c] = key.split("-").map(Number);
    const cell = board[r][c];
    if (cell.mahjong) collectMahjong(cell.mahjong);
    board[r][c] = { filled: false, color: "", mahjong: null };
  });
  renderBoard();
  return rowsToClear.length + colsToClear.length;
}

function collectMahjong(value) {
  if (!collected[value - 1]) {
    collected[value - 1] = true;
    const slot = mahjongBarEl.querySelector(`.mahjong-slot[data-value="${value}"]`);
    if (slot) slot.classList.add("collected");
    if (collected.every(Boolean)) {
      statusEl.textContent = "已集齐 1-9 饼，恭喜！继续挑战更高分吧。";
    }
  }
}

function isGameOver() {
  return pieces
    .filter((p) => !p.used)
    .every((p) => !canPlaceAny(p));
}

function canPlaceAny(piece) {
  for (let r = 0; r < BOARD_SIZE; r += 1) {
    for (let c = 0; c < BOARD_SIZE; c += 1) {
      const positions = piece.shape.map(([x, y]) => ({ r: r + y, c: c + x }));
      if (canPlace(positions)) return true;
    }
  }
  return false;
}

function getCellEl(r, c) {
  return boardEl.querySelector(`.cell[data-row="${r}"][data-col="${c}"]`);
}

function createBingSvg(value) {
  const dots = getDotPattern(value);
  const dotColors = {
    r: "#e54343",
    g: "#2ea862",
    b: "#2f6df5",
  };
  const dotsSvg = dots
    .map((d) => `<circle cx="${d.x}" cy="${d.y}" r="${d.r}" fill="${dotColors[d.c]}" />`)
    .join("");
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="64" height="90" viewBox="0 0 64 90">
      <rect x="6" y="6" width="52" height="78" rx="8" fill="#fefefe" stroke="#e3ded6" stroke-width="2"/>
      ${dotsSvg}
    </svg>
  `;
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
}

function getDotPattern(value) {
  const grid = [
    { x: 22, y: 26 },
    { x: 42, y: 26 },
    { x: 22, y: 45 },
    { x: 42, y: 45 },
    { x: 22, y: 64 },
    { x: 42, y: 64 },
    { x: 32, y: 35 },
    { x: 32, y: 55 },
    { x: 32, y: 26 },
  ];
  const map = {
    1: [{ idx: 6, c: "r" }],
    2: [
      { idx: 0, c: "g" },
      { idx: 5, c: "g" },
    ],
    3: [
      { idx: 0, c: "g" },
      { idx: 6, c: "r" },
      { idx: 5, c: "g" },
    ],
    4: [
      { idx: 0, c: "b" },
      { idx: 1, c: "b" },
      { idx: 4, c: "b" },
      { idx: 5, c: "b" },
    ],
    5: [
      { idx: 0, c: "b" },
      { idx: 1, c: "b" },
      { idx: 6, c: "r" },
      { idx: 4, c: "b" },
      { idx: 5, c: "b" },
    ],
    6: [
      { idx: 0, c: "g" },
      { idx: 1, c: "g" },
      { idx: 2, c: "g" },
      { idx: 3, c: "g" },
      { idx: 4, c: "g" },
      { idx: 5, c: "g" },
    ],
    7: [
      { idx: 0, c: "g" },
      { idx: 1, c: "g" },
      { idx: 2, c: "g" },
      { idx: 3, c: "g" },
      { idx: 4, c: "g" },
      { idx: 5, c: "g" },
      { idx: 6, c: "r" },
    ],
    8: [
      { idx: 0, c: "b" },
      { idx: 1, c: "b" },
      { idx: 2, c: "b" },
      { idx: 3, c: "b" },
      { idx: 4, c: "b" },
      { idx: 5, c: "b" },
      { idx: 6, c: "r" },
      { idx: 7, c: "r" },
    ],
    9: [
      { idx: 0, c: "b" },
      { idx: 1, c: "b" },
      { idx: 2, c: "b" },
      { idx: 3, c: "b" },
      { idx: 4, c: "b" },
      { idx: 5, c: "b" },
      { idx: 6, c: "r" },
      { idx: 7, c: "r" },
      { idx: 8, c: "r" },
    ],
  };
  return (map[value] || []).map((d) => ({ x: grid[d.idx].x, y: grid[d.idx].y, r: 5, c: d.c }));
}

function start() {
  initMahjongBar();
  initBoard();
  generatePieces();
  renderBoard();
}

start();
