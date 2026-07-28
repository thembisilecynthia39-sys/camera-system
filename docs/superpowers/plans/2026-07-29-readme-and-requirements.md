# README and Requirements Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide a complete root quick start and unambiguous production and development dependency entry points.

**Architecture:** Keep `requirements/jetson.txt` as the installer’s production source of truth. Add thin conventional include files and a dependency guide, while turning the root README into the task-oriented entry point that links to deeper component documentation.

**Tech Stack:** Markdown, pip requirements files, pytest, Bash, JetPack 5.1.1, Python 3.8

## Global Constraints

- Jetson Orin Nano with JetPack 5.1.1 is the production baseline.
- Do not add PySide6, PyQt5, pip OpenCV, CUDA, TensorRT, Torch, or ONNX to production requirements.
- Keep `requirements/jetson.txt` as the exact production lock consumed by `scripts/jetson/install.sh`.
- Keep development tools compatible with Python 3.8.
- Do not duplicate standalone component API documentation in the root README.

---

### Task 1: Dependency entry points

**Files:**
- Create: `requirements.txt`
- Create: `requirements/dev.txt`
- Create: `requirements/README.md`
- Test: `tests/app_shell/test_documentation.py`

**Interfaces:**
- Consumes: `requirements/jetson.txt` as the production dependency lock.
- Produces: `requirements.txt` for conventional runtime installation and `requirements/dev.txt` for repository testing.

- [ ] **Step 1: Write failing dependency-layout tests**

Add tests that assert:

```python
assert (PROJECT_ROOT / "requirements.txt").read_text().strip().endswith(
    "-r requirements/jetson.txt"
)
assert "-r jetson.txt" in (
    PROJECT_ROOT / "requirements/dev.txt"
).read_text()
assert "pytest>=7,<9" in (
    PROJECT_ROOT / "requirements/dev.txt"
).read_text()
```

Also assert that production requirement lines do not install `PySide6`,
`PyQt5`, `opencv-python`, `opencv-contrib-python`, `torch`, `onnx`,
`tensorrt`, or CUDA packages.

- [ ] **Step 2: Run tests and confirm missing-file failures**

Run:

```bash
.venv-jetson/bin/python -m pytest -q tests/app_shell/test_documentation.py
```

Expected: failure because the new requirement entry points do not exist.

- [ ] **Step 3: Add requirement entry points and guide**

Create:

```text
# requirements.txt
-r requirements/jetson.txt
```

Create `requirements/dev.txt` with:

```text
-r jetson.txt
pytest>=7,<9
```

Document the runtime, development, system-owned, and optional model-conversion
dependency groups in `requirements/README.md`, including exact install and
diagnosis commands.

- [ ] **Step 4: Run dependency-layout tests**

Run:

```bash
.venv-jetson/bin/python -m pytest -q tests/app_shell/test_documentation.py
```

Expected: all tests pass.

- [ ] **Step 5: Commit dependency documentation**

```bash
git add requirements.txt requirements/dev.txt requirements/README.md tests/app_shell/test_documentation.py
git commit -m "docs: complete dependency installation entry points"
```

### Task 2: Root quick start

**Files:**
- Modify: `README.md`
- Modify: `docs/README.md`
- Test: `tests/app_shell/test_documentation.py`

**Interfaces:**
- Consumes: installation scripts, `config/examples/settings.yaml`, requirement entry points, and component READMEs.
- Produces: one root onboarding flow for operators and developers.

- [ ] **Step 1: Write failing README coverage tests**

Assert that `README.md` contains these user-facing sections and commands:

```python
required_text = (
    "## 支持平台",
    "## 快速开始",
    "./scripts/jetson/install.sh",
    "./scripts/jetson/diagnose.sh",
    "./scripts/jetson/run.sh",
    "## 配置",
    "## 取消、超时与安全退出",
    "## 开发与测试",
    "requirements/dev.txt",
    "## 常见问题",
)
```

Assert that every relative Markdown link in the root README resolves to a
repository path.

- [ ] **Step 2: Run tests and confirm missing-section failures**

Run:

```bash
.venv-jetson/bin/python -m pytest -q tests/app_shell/test_documentation.py
```

Expected: failure for missing README sections.

- [ ] **Step 3: Rewrite README as the root operational guide**

Include platform requirements, architecture overview, quick start, WSL
configuration, end-to-end workflow, cancellation limits, directories,
development commands, release commands, troubleshooting, and documentation
links. State that large PLY, device commands, and already-sent HTTP requests
cancel at chunk or timeout boundaries rather than instantly.

Add `requirements/README.md` to `docs/README.md`.

- [ ] **Step 4: Run documentation tests**

Run:

```bash
.venv-jetson/bin/python -m pytest -q tests/app_shell/test_documentation.py
```

Expected: all tests pass.

- [ ] **Step 5: Commit README completion**

```bash
git add README.md docs/README.md tests/app_shell/test_documentation.py
git commit -m "docs: complete repository quick start"
```

### Task 3: Final verification

**Files:**
- Verify: `README.md`
- Verify: `requirements.txt`
- Verify: `requirements/jetson.txt`
- Verify: `requirements/dev.txt`
- Verify: `requirements/README.md`

**Interfaces:**
- Consumes: completed documentation and dependency layout.
- Produces: a release-ready, tested documentation update.

- [ ] **Step 1: Verify requirement files resolve**

Run:

```bash
.venv-jetson/bin/python -m pip install --dry-run --no-deps -r requirements.txt
.venv-jetson/bin/python -m pip install --dry-run --no-deps -r requirements/dev.txt
```

Expected: pip parses both include chains successfully without changing the
environment.

- [ ] **Step 2: Run project checks**

Run:

```bash
.venv-jetson/bin/python -m pytest -q
./scripts/jetson/diagnose.sh --json
git diff --check
```

Expected: tests pass, diagnostics have no core failures, and the diff check is
clean.

- [ ] **Step 3: Review repository state**

Run:

```bash
git status --short
git log --oneline -5
```

Expected: only intentional documentation changes remain, or the worktree is
clean after the task commits.

