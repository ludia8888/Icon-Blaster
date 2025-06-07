[CLAUDE-RULES.md]
“Write Code with *Minimum* Bug Risk – 7-Step Engineering Playbook”

> **Context**  
> You are coding a new feature. Your top priority is to **reduce the probability of introducing bugs**. Apply the following evidence-based strategies, which combine *systemic thinking, practical tooling, and collaborative process*.

---

### 1 ️⃣  Design & Build in Small Pieces  *(Modularization + Single-Responsibility)*
- **Principle** High complexity ⇒ exponential bug risk. Cohesion↑ & Coupling↓ ⇒ errors↓.  
- **Rules** One function = one job, keep it ≤ 10 – 30 lines.  
  Layer complex flows (e.g., `handler → service → logic → utils`).

### 2 ️⃣  Write Tests First (TDD) or at Least Unit Tests
- **Evidence** Google’s 15-year study: higher coverage slashes maintenance cost.  
- **Do** For every core behavior add a test (`pytest`, `unittest`, `jest`, `vitest`).  
  Always test side-effects (DB, files).

### 3 ️⃣  Use Static Analysis (Lint + Type Check)
- **Why** Machines catch repetitive human mistakes instantly.  
- **Tools**  
  - *Python*: `mypy`, `ruff`, `flake8`  
  - *JS/TS*: `eslint`, `prettier`, `typescript --strict`  
  Auto-run in IDE (`.vscode/settings.json` or Cursor).

### 4 ️⃣  Commit Small & Often  *(Git + Branch Strategy)*
- Track history; use `git blame / bisect` to locate bugs fast.  
- Create feature-scoped branches (`feature/color-detection`).  
- Commit messages explain **why**, not just **what**.

### 5 ️⃣  Enforce Code Review / Rubber-Duck Routine
- Explaining code exposes hidden logic flaws.  
- Describe the flow to ChatGPT, a teammate, or an imaginary duck before merging.  
- Ask yourself: “Can I clearly justify this design?”

### 6 ️⃣  Prefer Logging over Ad-hoc Debugging  *(Observability)*
- Post-deploy debugging is harder than pre-deploy insight.  
- Set log levels (`INFO | DEBUG | ERROR`).  
- Log entry/exit of key paths & failure conditions  
  (*Python*: `logging`, *JS*: `winston`, `loglevel`).

### 7 ️⃣  Specification-Driven Coding (Explicit I/O Contracts)
- Define input → process → output **before** implementation.  
- Use type hints / interfaces to freeze those contracts (`Dict[str, Any]` → precise types).  
- Apply to APIs, models, DB schemas alike.

---

#### ✳️ Bonus – Use AI Tools, but Verify
Copilot, Cursor, ChatGPT = pattern engines ~70-80 % accurate.  
Double-check DB logic, async flows, edge cases.  
Always ask: “*Why did I choose this solution?*”
---
*이 문서는 Claude가 프로젝트를 더 잘 이해하고 도움을 줄 수 있도록 작성되었습니다.*