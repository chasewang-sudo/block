(() => {
  const GRID_SIZE = 8;
  const GOAL_TARGET = 12;
  const MAX_MOLES = 20;
  const MOLE_REWARD = 0.1;
  const DRAG_LIFT_Y = 80;

  const SHAPES = [
    { id: 'dot', s: [[1]] },
    { id: 'line2', s: [[1, 1]] },
    { id: 'line3', s: [[1, 1, 1]] },
    { id: 'line4', s: [[1, 1, 1, 1]] },
    { id: 'sq2', s: [[1, 1], [1, 1]] },
    { id: 'L3', s: [[1, 0], [1, 0], [1, 1]] },
    { id: 'L3r', s: [[0, 1], [0, 1], [1, 1]] },
    { id: 'T', s: [[1, 1, 1], [0, 1, 0]] },
    { id: 'S', s: [[0, 1, 1], [1, 1, 0]] },
    { id: 'Z', s: [[1, 1, 0], [0, 1, 1]] },
  ];

  const state = {
    grid: makeGrid(0),
    holes: makeGrid(0),
    moles: [],
    pieces: [],
    selectedPieceId: null,
    collected: 0,
    money: 0,
    gameActive: false,
    seed: 'PHASER_MIGRATION_V1',
  };

  const ui = {
    mount: document.getElementById('phaser-mount'),
    gate: document.getElementById('gate'),
    play: document.getElementById('play'),
    note: document.getElementById('migration-note'),
    goalStatus: document.getElementById('goal-status'),
    earnedStatus: document.getElementById('earned-status'),
    pieceZone: document.getElementById('piece-zone'),
    resultOverlay: document.getElementById('result-overlay'),
    resultImage: document.getElementById('result-image'),
    resultRestart: document.getElementById('result-restart'),
  };

  const canvasAssets = {
    block: new Image(),
    hole: new Image(),
    mole: new Image(),
  };
  canvasAssets.block.src = '../pic/block.png';
  canvasAssets.hole.src = '../pic/hole3.jpg';
  canvasAssets.mole.src = '../pic/mole.png';
  [canvasAssets.block, canvasAssets.hole, canvasAssets.mole].forEach((img) => {
    img.addEventListener('load', () => {
      if (ui.pieceZone && state.pieces.length) renderPieceSlots();
    });
  });

  const drag = {
    active: false,
    pieceId: null,
    ghost: null,
    overBoard: false,
    candidate: null,
    pointerId: null,
  };

  if (!window.Phaser) {
    ui.play.textContent = 'Phaser Missing';
    return;
  }

  function makeGrid(fill) {
    return Array.from({ length: GRID_SIZE }, () => Array(GRID_SIZE).fill(fill));
  }

  function applyInitialBoardPreset() {
    // Temporary fixed opener for migration parity visibility.
    const preset = [
      [1, 1, 1, 0, 0, 0, 0, 0],
      [1, 0, 1, 1, 1, 0, 0, 0],
      [1, 1, 1, 0, 1, 0, 0, 0],
      [0, 0, 1, 1, 1, 0, 0, 0],
      [0, 0, 0, 0, 1, 0, 0, 0],
      [0, 0, 0, 0, 0, 0, 0, 0],
      [0, 0, 0, 0, 0, 0, 0, 0],
      [0, 0, 0, 0, 0, 0, 0, 0],
    ];
    for (let r = 0; r < GRID_SIZE; r++) {
      for (let c = 0; c < GRID_SIZE; c++) state.grid[r][c] = preset[r][c];
    }
  }

  function randomItem(arr) {
    return arr[Math.floor(Math.random() * arr.length)];
  }

  function shapeCells(shape) {
    const out = [];
    for (let r = 0; r < shape.length; r++) {
      for (let c = 0; c < shape[r].length; c++) {
        if (shape[r][c]) out.push({ r, c });
      }
    }
    return out;
  }

  function canPlace(shape, top, left) {
    const cells = shapeCells(shape);
    for (const cell of cells) {
      const r = top + cell.r;
      const c = left + cell.c;
      if (r < 0 || r >= GRID_SIZE || c < 0 || c >= GRID_SIZE) return false;
      if (state.grid[r][c]) return false;
    }
    return true;
  }

  function findClearLines() {
    const rows = [];
    const cols = [];
    for (let r = 0; r < GRID_SIZE; r++) {
      if (state.grid[r].every((v) => v === 1)) rows.push(r);
    }
    for (let c = 0; c < GRID_SIZE; c++) {
      let full = true;
      for (let r = 0; r < GRID_SIZE; r++) {
        if (state.grid[r][c] !== 1) {
          full = false;
          break;
        }
      }
      if (full) cols.push(c);
    }
    return { rows, cols };
  }

  function hasAnyMove() {
    const alive = state.pieces.filter((p) => !p.used);
    for (const piece of alive) {
      for (let r = 0; r < GRID_SIZE; r++) {
        for (let c = 0; c < GRID_SIZE; c++) {
          if (canPlace(piece.shape, r, c)) return true;
        }
      }
    }
    return false;
  }

  function gameOver(reason) {
    state.gameActive = false;
    ui.note.textContent = `Game Over (${reason}) | collected:${state.collected}/${MAX_MOLES} money:$${state.money.toFixed(2)}`;
    if (reason === 'no-space') {
      ui.resultImage.src = '../pic/move.png';
      ui.resultOverlay.classList.remove('hidden');
    }
  }

  class RenderScene extends Phaser.Scene {
    constructor() {
      super('render_scene');
      this.cellSize = 0;
      this.gridSprites = [];
      this.moleSprites = new Map();
      this.previewLayer = null;
      this.fxLayer = null;
      this.clearOverlay = null;
    }

    preload() {
      this.load.image('block', '../pic/block.png');
      this.load.image('hole', '../pic/hole3.jpg');
      this.load.image('mole', '../pic/mole.png');
      this.load.image('hammer', '../pic/hammer.png');
    }

    create() {
      this.cellSize = this.scale.width / GRID_SIZE;
      this.previewLayer = this.add.container(0, 0);
      this.previewLayer.setDepth(30);
      this.fxLayer = this.add.container(0, 0);
      this.fxLayer.setDepth(50);

      for (let r = 0; r < GRID_SIZE; r++) {
        this.gridSprites[r] = [];
        for (let c = 0; c < GRID_SIZE; c++) {
          const x = c * this.cellSize + this.cellSize / 2;
          const y = r * this.cellSize + this.cellSize / 2;
          const bg = this.add.rectangle(x, y, this.cellSize - 4, this.cellSize - 4, 0x5c3222).setStrokeStyle(2, 0x432317).setDepth(1);
          this.gridSprites[r][c] = { bg, block: null, hole: null };
        }
      }
      this.renderFromState('ready');
    }

    clearPreview() {
      this.previewLayer.removeAll(true);
    }

    drawPreview(piece, top, left, valid, clearLines) {
      this.clearPreview();
      const cells = shapeCells(piece.shape);
      cells.forEach((cell) => {
        const r = top + cell.r;
        const c = left + cell.c;
        if (r < 0 || r >= GRID_SIZE || c < 0 || c >= GRID_SIZE) return;
        const x = c * this.cellSize + this.cellSize / 2;
        const y = r * this.cellSize + this.cellSize / 2;
        if (valid) {
          const b = this.add.image(x, y, 'block').setDisplaySize(this.cellSize - 6, this.cellSize - 6).setAlpha(0.72);
          this.previewLayer.add(b);
          if (piece.hasMole) {
            const h = this.add.image(x, y, 'hole').setDisplaySize(this.cellSize - 6, this.cellSize - 6).setAlpha(0.65);
            this.previewLayer.add(h);
          }
          if (piece.hasMole && piece.molePos && piece.molePos.r === cell.r && piece.molePos.c === cell.c) {
            const m = this.add.image(x, y, 'mole').setDisplaySize(this.cellSize * 0.5, this.cellSize * 0.5).setAlpha(0.9);
            this.previewLayer.add(m);
          }
        } else {
          const rect = this.add.rectangle(x, y, this.cellSize - 6, this.cellSize - 6, 0xea6d6d, 0.7);
          this.previewLayer.add(rect);
        }
      });

      const lineColor = valid ? 0xffcc43 : 0xb14444;
      clearLines.rows.forEach((r) => {
        for (let c = 0; c < GRID_SIZE; c++) {
          const x = c * this.cellSize + this.cellSize / 2;
          const y = r * this.cellSize + this.cellSize / 2;
          const o = this.add.rectangle(x, y, this.cellSize - 3, this.cellSize - 3, lineColor, 0.35);
          this.previewLayer.add(o);
        }
      });
      clearLines.cols.forEach((c) => {
        for (let r = 0; r < GRID_SIZE; r++) {
          const x = c * this.cellSize + this.cellSize / 2;
          const y = r * this.cellSize + this.cellSize / 2;
          const o = this.add.rectangle(x, y, this.cellSize - 3, this.cellSize - 3, lineColor, 0.35);
          this.previewLayer.add(o);
        }
      });
    }

    playInvalidHint(top, left, shape) {
      const safeLeft = Math.max(0, Math.min(left, GRID_SIZE - shape[0].length));
      const safeTop = Math.max(0, Math.min(top, GRID_SIZE - shape.length));
      const x = (safeLeft + shape[0].length * 0.5) * this.cellSize;
      const y = (safeTop + shape.length * 0.5) * this.cellSize;
      const container = this.add.container(x, y);
      const cells = shapeCells(shape);
      cells.forEach((cell) => {
        const px = (cell.c - shape[0].length / 2 + 0.5) * this.cellSize;
        const py = (cell.r - shape.length / 2 + 0.5) * this.cellSize;
        const rect = this.add.rectangle(px, py, this.cellSize - 8, this.cellSize - 8, 0xff6767, 0.7);
        container.add(rect);
      });
      this.fxLayer.add(container);
      this.tweens.add({
        targets: container,
        x: x + 5,
        duration: 50,
        yoyo: true,
        repeat: 3,
        onComplete: () => container.destroy(),
      });
    }

    refreshBoard() {
      for (let r = 0; r < GRID_SIZE; r++) {
        for (let c = 0; c < GRID_SIZE; c++) {
          const cell = this.gridSprites[r][c];
          if (cell.block) {
            cell.block.destroy();
            cell.block = null;
          }
          if (cell.hole) {
            cell.hole.destroy();
            cell.hole = null;
          }

          const x = c * this.cellSize + this.cellSize / 2;
          const y = r * this.cellSize + this.cellSize / 2;
          if (state.grid[r][c]) {
            cell.block = this.add.image(x, y, 'block').setDisplaySize(this.cellSize - 4, this.cellSize - 4).setDepth(8);
          }
          if (state.holes[r][c]) {
            cell.hole = this.add.image(x, y, 'hole').setDisplaySize(this.cellSize - 4, this.cellSize - 4).setAlpha(0.9).setDepth(9);
          }
        }
      }
    }

    refreshMoles() {
      const activeKeys = new Set();
      state.moles.forEach((m) => {
        const key = `${m.id}`;
        activeKeys.add(key);
        const x = m.c * this.cellSize + this.cellSize / 2;
        const y = m.r * this.cellSize + this.cellSize / 2;

        if (!this.moleSprites.has(key)) {
          const sprite = this.add.image(x, y, 'mole').setDisplaySize(this.cellSize * 0.8, this.cellSize * 0.8).setDepth(20);
          this.moleSprites.set(key, sprite);
        } else {
          const sprite = this.moleSprites.get(key);
          this.tweens.add({ targets: sprite, x, y, duration: 180, ease: 'Sine.Out' });
        }
      });

      this.moleSprites.forEach((sprite, key) => {
        if (!activeKeys.has(key)) {
          sprite.destroy();
          this.moleSprites.delete(key);
        }
      });
    }

    animateClear(rows, cols) {
      const cells = [];
      rows.forEach((r) => {
        for (let c = 0; c < GRID_SIZE; c++) cells.push({ r, c });
      });
      cols.forEach((c) => {
        for (let r = 0; r < GRID_SIZE; r++) cells.push({ r, c });
      });
      cells.forEach((cell, i) => {
        const x = cell.c * this.cellSize + this.cellSize / 2;
        const y = cell.r * this.cellSize + this.cellSize / 2;
        const chip = this.add.rectangle(x, y, this.cellSize - 6, this.cellSize - 6, 0xffe48a, 0.75);
        this.fxLayer.add(chip);
        this.tweens.add({
          targets: chip,
          alpha: 0,
          scaleX: 0.2,
          scaleY: 0.2,
          duration: 160,
          delay: i * 12,
          onComplete: () => chip.destroy(),
        });
      });
    }

    hammerMole(mole) {
      const x = mole.c * this.cellSize + this.cellSize / 2;
      const y = mole.r * this.cellSize + this.cellSize / 2;
      const hammer = this.add.image(x + 18, y - 26, 'hammer').setDisplaySize(56, 56).setDepth(40).setScale(1.28);
      this.fxLayer.add(hammer);
      this.tweens.add({
        targets: hammer,
        scaleX: 1,
        scaleY: 1,
        x,
        y,
        duration: 220,
        onComplete: () => {
          const burst = this.add.text(x, y - 6, '$', { fontSize: '26px', fontStyle: '900', color: '#5DFF9A' }).setOrigin(0.5).setDepth(41);
          this.fxLayer.add(burst);
          this.tweens.add({
            targets: burst,
            y: -24,
            alpha: 0,
            duration: 500,
            onComplete: () => burst.destroy(),
          });
          hammer.destroy();
        },
      });
    }

    renderFromState(status = 'sync') {
      this.refreshBoard();
      this.refreshMoles();
      ui.note.textContent = `Phaser gameplay baseline (${status}) | blocks:${state.grid.flat().filter(Boolean).length} holes:${state.holes.flat().filter(Boolean).length} moles:${state.moles.length}`;
    }
  }

  const game = new Phaser.Game({
    type: Phaser.AUTO,
    parent: ui.mount,
    width: 360,
    height: 360,
    transparent: true,
    scene: [RenderScene],
    input: { touch: true, mouse: true },
    audio: { noAudio: true },
  });

  function buildPiece(hasMoleForce = false) {
    const shapeObj = randomItem(SHAPES);
    const cells = shapeCells(shapeObj.s);
    const moleIndex = Math.floor(Math.random() * cells.length);
    const molePos = cells[moleIndex];
    const hasMole = hasMoleForce || Math.random() < 0.4;
    return {
      id: `${Date.now()}_${Math.random().toString(16).slice(2)}`,
      shape: shapeObj.s.map((row) => [...row]),
      hasMole,
      molePos: hasMole ? { ...molePos } : null,
      used: false,
    };
  }

  function createPieceBatch(forceOneMole = false) {
    const out = [buildPiece(false), buildPiece(false), buildPiece(false)];
    if (forceOneMole && !out.some((p) => p.hasMole)) out[0] = buildPiece(true);
    return out;
  }

  function drawPieceOnCanvas(piece, canvas) {
    const ctx = canvas.getContext('2d');
    const rows = piece.shape.length;
    const cols = piece.shape[0].length;
    const cell = Math.floor(Math.min(canvas.width / cols, canvas.height / rows));
    const padX = Math.floor((canvas.width - cols * cell) / 2);
    const padY = Math.floor((canvas.height - rows * cell) / 2);

    ctx.clearRect(0, 0, canvas.width, canvas.height);
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        if (!piece.shape[r][c]) continue;
        const x = padX + c * cell;
        const y = padY + r * cell;
        if (canvasAssets.block.complete) {
          ctx.drawImage(canvasAssets.block, x + 1, y + 1, cell - 2, cell - 2);
        } else {
          ctx.fillStyle = '#59c14d';
          ctx.fillRect(x + 2, y + 2, cell - 4, cell - 4);
        }
        if (piece.hasMole) {
          if (canvasAssets.hole.complete) {
            ctx.globalAlpha = 0.9;
            ctx.drawImage(canvasAssets.hole, x + 1, y + 1, cell - 2, cell - 2);
            ctx.globalAlpha = 1;
          } else {
            ctx.fillStyle = 'rgba(80, 58, 27, 0.78)';
            ctx.beginPath();
            ctx.ellipse(x + cell / 2, y + cell * 0.66, cell * 0.27, cell * 0.15, 0, 0, Math.PI * 2);
            ctx.fill();
          }
        }
        if (piece.hasMole && piece.molePos && piece.molePos.r === r && piece.molePos.c === c) {
          if (canvasAssets.mole.complete) {
            const ms = Math.max(10, cell * 0.55);
            ctx.drawImage(canvasAssets.mole, x + (cell - ms) / 2, y + (cell - ms) / 2 - 1, ms, ms);
          } else {
            ctx.fillStyle = '#f6d465';
            ctx.beginPath();
            ctx.arc(x + cell / 2, y + cell * 0.36, Math.max(3, cell * 0.11), 0, Math.PI * 2);
            ctx.fill();
          }
        }
      }
    }
  }

  function renderPieceSlots() {
    ui.pieceZone.innerHTML = '';
    state.pieces.forEach((piece) => {
      const slot = document.createElement('button');
      slot.className = `piece-slot${piece.used ? ' used' : ''}${state.selectedPieceId === piece.id ? ' selected' : ''}`;
      slot.dataset.pieceId = piece.id;
      slot.type = 'button';

      const cv = document.createElement('canvas');
      cv.className = 'piece-canvas';
      cv.width = 86;
      cv.height = 86;
      drawPieceOnCanvas(piece, cv);
      slot.appendChild(cv);

      slot.addEventListener('pointerdown', (e) => {
        if (!state.gameActive || piece.used) return;
        e.preventDefault();
        startDrag(piece.id, e);
      });
      ui.pieceZone.appendChild(slot);
    });
  }

  function getPieceById(pieceId) {
    return state.pieces.find((p) => p.id === pieceId);
  }

  function boardCandidateFromClient(clientX, clientY, piece) {
    const rect = ui.mount.getBoundingClientRect();
    const scene = game.scene.getScene('render_scene');
    const cellSize = scene.cellSize || rect.width / GRID_SIZE;

    const localX = clientX - rect.left;
    const localY = clientY - rect.top;
    const onBoard = localX >= 0 && localX <= rect.width && localY >= 0 && localY <= rect.height;

    const anchorR = Math.floor(piece.shape.length / 2);
    const anchorC = Math.floor(piece.shape[0].length / 2);

    const cellR = Math.floor(localY / cellSize);
    const cellC = Math.floor(localX / cellSize);
    const top = cellR - anchorR;
    const left = cellC - anchorC;
    return { onBoard, top, left, localX, localY, cellSize };
  }

  function resolveSnapCandidate(pointerCandidate, piece) {
    if (!pointerCandidate.onBoard) return { ...pointerCandidate, valid: false, snapped: false };

    const rows = piece.shape.length;
    const cols = piece.shape[0].length;
    const pointerCellX = pointerCandidate.localX / pointerCandidate.cellSize;
    const pointerCellY = pointerCandidate.localY / pointerCandidate.cellSize;

    let best = null;
    for (let top = 0; top <= GRID_SIZE - rows; top++) {
      for (let left = 0; left <= GRID_SIZE - cols; left++) {
        if (!canPlace(piece.shape, top, left)) continue;
        const centerX = left + cols / 2;
        const centerY = top + rows / 2;
        const dx = centerX - pointerCellX;
        const dy = centerY - pointerCellY;
        const score = dx * dx + dy * dy;
        if (!best || score < best.score) best = { top, left, score };
      }
    }

    if (!best) return { ...pointerCandidate, valid: false, snapped: false };
    return {
      ...pointerCandidate,
      top: best.top,
      left: best.left,
      valid: true,
      snapped: true,
    };
  }

  function startDrag(pieceId, event) {
    state.selectedPieceId = pieceId;
    renderPieceSlots();

    const piece = getPieceById(pieceId);
    if (!piece) return;

    drag.active = true;
    drag.pieceId = pieceId;
    drag.pointerId = event.pointerId || null;

    const ghost = document.createElement('canvas');
    ghost.className = 'drag-ghost';
    ghost.width = 92;
    ghost.height = 92;
    drawPieceOnCanvas(piece, ghost);
    document.body.appendChild(ghost);
    drag.ghost = ghost;

    updateDrag(event.clientX, event.clientY);
    window.addEventListener('pointermove', onPointerMove, { passive: false });
    window.addEventListener('pointerup', onPointerUp, { passive: false });
  }

  function stopDrag() {
    drag.active = false;
    drag.pieceId = null;
    drag.candidate = null;
    if (drag.ghost) {
      drag.ghost.remove();
      drag.ghost = null;
    }
    const scene = game.scene.getScene('render_scene');
    if (scene && scene.scene.isActive()) scene.clearPreview();
    window.removeEventListener('pointermove', onPointerMove);
    window.removeEventListener('pointerup', onPointerUp);
  }

  function onPointerMove(e) {
    if (!drag.active) return;
    e.preventDefault();
    updateDrag(e.clientX, e.clientY);
  }

  function updateDrag(clientX, clientY) {
    const piece = getPieceById(drag.pieceId);
    if (!piece) return;

    const ghostX = clientX;
    const ghostY = clientY - DRAG_LIFT_Y;

    if (drag.ghost) {
      drag.ghost.style.left = `${ghostX}px`;
      drag.ghost.style.top = `${ghostY}px`;
      drag.ghost.style.opacity = '0.86';
    }

    const scene = game.scene.getScene('render_scene');
    if (!scene || !scene.scene.isActive()) return;

    // Placement follows the lifted block visual position, not finger position.
    const pointerCandidate = boardCandidateFromClient(ghostX, ghostY, piece);
    const candidate = resolveSnapCandidate(pointerCandidate, piece);
    drag.overBoard = candidate.onBoard;
    drag.candidate = candidate;

    if (!candidate.onBoard) {
      scene.clearPreview();
      return;
    }

    if (candidate.valid) {
      const cells = shapeCells(piece.shape);
      cells.forEach((cell) => {
        state.grid[candidate.top + cell.r][candidate.left + cell.c] = 1;
      });
      const clearLines = findClearLines();
      cells.forEach((cell) => {
        state.grid[candidate.top + cell.r][candidate.left + cell.c] = 0;
      });
      scene.drawPreview(piece, candidate.top, candidate.left, true, clearLines);
    } else {
      scene.drawPreview(piece, pointerCandidate.top, pointerCandidate.left, false, { rows: [], cols: [] });
    }
  }

  function onPointerUp(e) {
    if (!drag.active) return;
    e.preventDefault();

    const piece = getPieceById(drag.pieceId);
    const scene = game.scene.getScene('render_scene');
    const candidate = drag.candidate;

    if (!piece || !candidate || !candidate.onBoard || !candidate.valid || !canPlace(piece.shape, candidate.top, candidate.left)) {
      if (scene && candidate) scene.playInvalidHint(candidate.top, candidate.left, piece ? piece.shape : [[1]]);
      stopDrag();
      return;
    }

    placePiece(piece, candidate.top, candidate.left);
    stopDrag();
  }

  function placePiece(piece, top, left) {
    const scene = game.scene.getScene('render_scene');
    const cells = shapeCells(piece.shape);
    cells.forEach((cell) => {
      const r = top + cell.r;
      const c = left + cell.c;
      state.grid[r][c] = 1;
      if (piece.hasMole) state.holes[r][c] = 1;
    });

    if (piece.hasMole && piece.molePos && state.moles.length < 4) {
      state.moles.push({
        id: `${Date.now()}_${Math.random().toString(16).slice(2)}`,
        r: top + piece.molePos.r,
        c: left + piece.molePos.c,
      });
    }

    piece.used = true;
    const clearLines = findClearLines();
    if (clearLines.rows.length || clearLines.cols.length) {
      if (scene && scene.scene.isActive()) scene.animateClear(clearLines.rows, clearLines.cols);

      const captured = [];
      state.moles = state.moles.filter((m) => {
        if (clearLines.rows.includes(m.r) || clearLines.cols.includes(m.c)) {
          captured.push(m);
          return false;
        }
        return true;
      });

      clearLines.rows.forEach((r) => {
        state.grid[r].fill(0);
        state.holes[r].fill(0);
      });
      clearLines.cols.forEach((c) => {
        for (let r = 0; r < GRID_SIZE; r++) {
          state.grid[r][c] = 0;
          state.holes[r][c] = 0;
        }
      });

      captured.forEach((m, idx) => {
        setTimeout(() => {
          if (scene && scene.scene.isActive()) scene.hammerMole(m);
        }, 260 + idx * 120);
      });
      state.collected += captured.length;
      state.money += captured.length * MOLE_REWARD;
    }

    if (state.pieces.every((p) => p.used)) {
      state.pieces = createPieceBatch(state.moles.length === 0);
    }

    updateHud();
    renderPieceSlots();
    if (scene && scene.scene.isActive()) scene.renderFromState('place');

    if (state.collected >= MAX_MOLES) {
      gameOver('max-cap');
      return;
    }
    if (!hasAnyMove()) {
      gameOver('no-space');
    }
  }

  function updateHud() {
    const goalDone = Math.min(state.collected, GOAL_TARGET);
    ui.goalStatus.textContent = `${goalDone}/${GOAL_TARGET}`;
    ui.earnedStatus.textContent = `$${state.money.toFixed(2)}/$${(MAX_MOLES * MOLE_REWARD).toFixed(2)}`;
  }

  function resetState() {
    state.grid = makeGrid(0);
    state.holes = makeGrid(0);
    state.moles = [];
    state.collected = 0;
    state.money = 0;
    state.selectedPieceId = null;
    applyInitialBoardPreset();
    state.pieces = createPieceBatch(true);
    state.gameActive = true;
    ui.resultOverlay.classList.add('hidden');
    updateHud();
    renderPieceSlots();

    const scene = game.scene.getScene('render_scene');
    if (scene && scene.scene.isActive()) scene.renderFromState('reset');
    if (!hasAnyMove()) gameOver('no-space');
  }

  ui.play.addEventListener('click', () => {
    ui.gate.classList.add('hidden');
    resetState();
  });

  ui.resultRestart.addEventListener('click', () => {
    ui.gate.classList.add('hidden');
    resetState();
  });

  updateHud();
  state.pieces = createPieceBatch(true);
  renderPieceSlots();

  window.__PHASER_MIGRATION__ = {
    state,
    resetState,
    sync(status = 'manual') {
      const scene = game.scene.getScene('render_scene');
      if (scene && scene.scene.isActive()) scene.renderFromState(status);
    },
  };
})();
