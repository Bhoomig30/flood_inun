// ============================================================================
// FLOODWATCH — ML BRIDGE (Node -> Python subprocess)
// Spawns `python3 ml_serve.py serve` and forwards prediction requests.
// If Python/sklearn is unavailable, ML is disabled but the statistical
// engine keeps working — the dashboard labels which model produced output.
// ============================================================================

const { spawn } = require("child_process");
const path = require("path");

class MLBridge {
  constructor() {
    this.child = null;
    this.ready = false;
    this.available = null; // null = not checked, true/false = checked
    this.modelsLoaded = [];
    this._pending = new Map();
    this._nextId = 1;
    this._buffer = "";
    this._startAttempted = false;
  }

  start() {
    if (this._startAttempted) return;
    this._startAttempted = true;

    let python = null;
    for (const candidate of ["python3", "python"]) {
      try {
        const check = spawn(candidate, ["--version"], { stdio: "pipe" });
        const ok = new Promise((resolve) => {
          check.on("close", (code) => resolve(code === 0));
          check.on("error", () => resolve(false));
        });
        // Synchronous-style first check via a tiny race window is fragile;
        // instead just try python3 first and fall back if spawn errors.
        check.on("error", () => {});
        python = candidate;
        check.unref();
        break;
      } catch (err) {
        continue;
      }
    }
    if (!python) {
      this.available = false;
      this.disabledReason = "Python interpreter not found";
      return;
    }

    try {
      this.child = spawn(python, [path.join(__dirname, "ml_serve.py"), "serve"], {
        stdio: ["pipe", "pipe", "pipe"],
      });
    } catch (err) {
      this.available = false;
      this.disabledReason = "Failed to start ml_serve.py: " + err.message;
      return;
    }

    this.child.stdout.setEncoding("utf8");
    this.child.stdout.on("data", (chunk) => {
      this._buffer += chunk;
      let idx;
      while ((idx = this._buffer.indexOf("\n")) !== -1) {
        const line = this._buffer.slice(0, idx).trim();
        this._buffer = this._buffer.slice(idx + 1);
        if (!line) continue;
        this._handleLine(line);
      }
    });

    this.child.stderr.setEncoding("utf8");
    this.child.stderr.on("data", (chunk) => {
      // Keep stderr for diagnostics but do not spam the console.
      this._lastStderr = String(chunk).slice(0, 500);
    });

    this.child.on("error", (err) => {
      this.available = false;
      this.disabledReason = "python spawn error: " + err.message;
      this.child = null;
    });

    this.child.on("close", () => {
      this.ready = false;
      this.child = null;
      if (this.available) {
        this.available = false;
        this.disabledReason = "ml_serve.py exited";
      }
    });

    // Resolve readiness on the warm-up line.
    const warmupTimeout = setTimeout(() => {
      if (!this.ready && this.available === null) {
        this.available = false;
        this.disabledReason =
          "ml_serve.py did not answer (sklearn missing? run: pip install scikit-learn joblib)";
        try {
          this.child && this.child.kill();
        } catch (e) {}
      }
    }, 20000);

    this._warmupResolve = () => {
      clearTimeout(warmupTimeout);
    };
  }

  _handleLine(line) {
    let msg;
    try {
      msg = JSON.parse(line);
    } catch (err) {
      return;
    }

    if (msg && msg.data && msg.data.ready === false && this.available === null) {
      // ml_serve.py started but could not load models/dataset — disable now
      this.available = false;
      this.disabledReason = msg.data.error || "ml_serve.py failed to load models";
      if (this._warmupResolve) this._warmupResolve();
      try {
        this.child && this.child.kill();
      } catch (e) {}
      return;
    }

    if (msg && msg.data && msg.data.ready && this.available === null) {
      this.available = true;
      this.ready = true;
      this.modelsLoaded = msg.data.models_loaded || [];
      this.modelVersion = msg.data.model_version || null;
      this.datasetRows = msg.data.dataset_rows || null;
      this.datasetEnd = msg.data.dataset_end || null;
      if (this._warmupResolve) this._warmupResolve();
      return;
    }

    // Response to a pending request
    const id = msg.id;
    if (id && this._pending.has(id)) {
      const { resolve } = this._pending.get(id);
      this._pending.delete(id);
      resolve(msg);
    }
  }

  predict(referenceTime) {
    return new Promise((resolve) => {
      if (!this.child || !this.ready) {
        resolve({
          ok: false,
          error: this.disabledReason || "ML bridge not running",
        });
        return;
      }
      const id = this._nextId++;
      this._pending.set(id, { resolve });
      const req = JSON.stringify({
        id: id,
        cmd: "predict",
        reference_time: referenceTime || null,
      });
      try {
        this.child.stdin.write(req + "\n");
      } catch (err) {
        this._pending.delete(id);
        resolve({ ok: false, error: "ml_serve.py write failed: " + err.message });
      }
      // Timeout so the API never hangs on a stuck subprocess.
      setTimeout(() => {
        if (this._pending.has(id)) {
          this._pending.delete(id);
          resolve({ ok: false, error: "ML prediction timed out" });
        }
      }, 15000);
    });
  }

  status() {
    return {
      available: this.available === true && this.ready,
      models_loaded: this.modelsLoaded,
      model_version: this.modelVersion || null,
      dataset_rows: this.datasetRows || null,
      dataset_end: this.datasetEnd || null,
      reason: this.available === false ? this.disabledReason : null,
    };
  }
}

const mlBridge = new MLBridge();

module.exports = { mlBridge, MLBridge };
