(() => {
  "use strict";
  const root = document.getElementById("wb-root");
  if (!root) return;
  const id = root.dataset.studentId;
  const canvas = document.getElementById("wb-canvas");
  const ctx = canvas.getContext("2d");
  const status = document.getElementById("wb-status");
  const color = document.getElementById("wb-color");
  const csrf = root.querySelector('input[name="csrf"]').value;
  let strokes = [], active = null, dirty = false;
  const setStatus = text => { status.textContent = text; };
  function redraw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.lineWidth = 3;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    for (const stroke of strokes) {
      ctx.strokeStyle = stroke.color;
      ctx.fillStyle = stroke.color;
      ctx.beginPath();
      stroke.points.forEach(([x, y], index) => index ? ctx.lineTo(x, y) : ctx.moveTo(x, y));
      if (stroke.points.length === 1) {
        const [x, y] = stroke.points[0];
        ctx.fillRect(x, y, 2, 2);
      } else ctx.stroke();
    }
  }
  function point(event) {
    const rect = canvas.getBoundingClientRect();
    return [
      Math.max(0, Math.min(900, Math.round((event.clientX - rect.left) * 900 / rect.width))),
      Math.max(0, Math.min(520, Math.round((event.clientY - rect.top) * 520 / rect.height)))
    ];
  }
  canvas.addEventListener("pointerdown", event => {
    if (strokes.length >= 1200) { setStatus("Board is full. Undo or clear it."); return; }
    canvas.setPointerCapture(event.pointerId);
    active = {color: color.value, points: [point(event)]};
    strokes.push(active);
    dirty = true;
    redraw();
  });
  canvas.addEventListener("pointermove", event => {
    if (!active || active.points.length >= 300) return;
    active.points.push(point(event));
    redraw();
  });
  const stop = () => { active = null; if (dirty) setStatus("Unsaved changes"); };
  canvas.addEventListener("pointerup", stop);
  canvas.addEventListener("pointercancel", stop);
  document.getElementById("wb-undo").onclick = () => {
    strokes.pop(); dirty = true; redraw(); setStatus("Unsaved changes");
  };
  document.getElementById("wb-clear").onclick = () => {
    if (!confirm("Clear the entire board? Save to apply the change.")) return;
    strokes = []; dirty = true; redraw(); setStatus("Unsaved changes");
  };
  async function reload() {
    if (dirty && !confirm("Discard unsaved changes and reload the saved board?")) return;
    try {
      const response = await fetch("/whiteboard/" + id + "/data");
      if (!response.ok) throw Error("Unable to load board");
      const data = await response.json();
      strokes = data.strokes;
      dirty = false; redraw(); setStatus("Board loaded");
    } catch (error) { setStatus(error.message); }
  }
  document.getElementById("wb-reload").onclick = reload;
  document.getElementById("wb-save").onclick = async () => {
    try {
      const body = new URLSearchParams({csrf, strokes: JSON.stringify(strokes)});
      const response = await fetch("/whiteboard/" + id + "/save", {
        method: "POST", body, headers: {"Content-Type": "application/x-www-form-urlencoded"}
      });
      if (!response.ok) throw Error("Save failed (" + response.status + ")");
      dirty = false; setStatus("Board saved");
    } catch (error) { setStatus(error.message); }
  };
  window.addEventListener("beforeunload", event => {
    if (dirty) { event.preventDefault(); event.returnValue = ""; }
  });
  reload();
})();
