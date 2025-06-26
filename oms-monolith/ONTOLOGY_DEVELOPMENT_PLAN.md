# OMS Ontology Development Plan 

> **Scope Reminder**
> OMS (Ontology Metadata Service) *declares and versions the ontology meta‑model only*.
> Runtime concerns (object instance storage, graph traversal, permission evaluation, state propagation) are implemented by sibling services — **Object Storage**, **Object Set Service**, **Action Service**, and **Vertex**.
> This plan therefore focuses *exclusively* on **metadata definition, validation, and contract generation**.
**Always check what code already exists in the codebase**
---

## 100 % Compliance with *Ontology\_Requirements\_Document.md*

*Path: `/Users/sihyun/Desktop/ARRAKIS/SPICE/oms-monolith/Ontology_Requirements_Document.md`*

### Overview

The roadmap is organised into phases with clear milestones and tracking mechanisms. Existing well‑written sections were **retained verbatim**; only scope‑corrections were applied.

### Current Status Summary

| Category                | Implemented                                                                                                         | Pending                      |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------- | ---------------------------- |
| **Core Types**          | Object Type, Property, Shared Property, Link Type, Action Type, Interface, Data Type, Semantic Type, Struct Type   |                              |
| **Metadata Extensions** | Link Meta Flags (permissionInheritance, statePropagation, traversalMetadata), Graph Metadata Generator             |                              |
| **API Generation**      | Basic CRUD schemas, Semantic/Struct Type endpoints, GraphQL/OpenAPI schema generation with auto link fields       |                              |

> **Removed from OMS scope**: *Graph Index & Traversal*, *Runtime Permission Engine*, *Resolver Implementations*, *1 B+ instance load tests*.  These items are now tracked in the **Object Set / Action Service** backlogs.

---

## Phase 1 · Semantic Type Implementation (Week 1‑2)

**Goal**  Implement the Semantic (Value) Type system with domain constraints.

**Tasks**

1. **Create Semantic Type Model** `models/semantic_types.py`
   – Define `SemanticType` with regex / min‑max / enum validators
   – Add registry & ADR‑006 (Semantic Type Strategy)
2. **Property Integration**
   – Reference semantic types in `Property`
   – Validation hooks in **ValidationService**
   – CRUD + GraphQL endpoints
   – Pre‑defined types: `Email`, `URL`, `Phone`, `Currency`, etc.
3. **Testing & Docs**
   – Unit + integration tests
   – API docs update (OpenAPI & GraphQL)

**Deliverables**
`/models/semantic_types.py`, `/api/v1/semantic_types/*`, `/tests/test_semantic_types.py`

---

## Phase 2 · Struct Type Implementation (Week 3‑4)

**Goal**  Support multi‑field value aggregation (non‑nested).

**Key Rule**  *Nested Structs are not supported* (Foundry constraint). Return explicit error.

**Tasks**

1. `models/struct_types.py` – `StructType` with field map
2. Property enhancements + serializer
3. CRUD endpoints & GraphQL schema
4. Fallback validation for nesting violation

**Deliverables**
`/models/struct_types.py`, `/api/v1/struct_types/*`, `/core/schema/struct_validator.py`

---

## Phase 3 · **Link Meta Extensions** (Week 5‑6)

*Formerly “Graph Index & Traversal” — now limited to metadata flags*

**Goal**  Capture traversal‑related semantics *without implementing traversal logic*.

**Tasks**

1. **LinkType Flags**
   – `transitiveClosure: bool`
   – `cascadeDepth: int` (⩽ 5)
   – `symmetric: bool`
2. **Validation Rules**
   – Consistency checks (e.g., symmetric ⇒ bidirectional)
3. **Manifest Export**
   – Generate JSON manifest consumed by **Object Set Service** for index building

**Deliverables**
`/models/domain.py` (LinkType update), `/core/manifest/link_meta_exporter.py`

---

## Phase 4 · **Propagation Rule Metadata** (Week 7‑8)

*Runtime engine lives in Action Service; OMS only stores rules & publishes manifests.*

**Goal**  Model permission & state inheritance policies.

**Tasks**

1. **LinkType Enhancements**
   – `permissionInheritance: "none"|"parent"|"custom"`
   – `statePropagation: "none"|"forward"|"reverse"|"both"`
2. **Rule Manifest Generator**
   – Produce dictionary file → pushed to Action Service
   – Webhook for hot‑reload
3. **Security Metadata Tests**

**Deliverables**
`/core/security/rule_manifest.py`, unit tests, updated ADR‑007 (Propagation Semantics)

---

## Phase 5 · Enhanced API Schema Generation (Week 9‑10)

**Goal**  Auto‑generate GraphQL/OpenAPI schemas *only*; resolvers are external.

**Tasks**

1. **Schema Generator** `core/api/schema_generator.py`
   – Produce `SingleLink` / `LinkSet` field types
   – Emit SDL + OpenAPI documents
2. **SDK Types**
   – Update Python & TypeScript SDK models

**Deliverables**
Generated SDL, OpenAPI spec, updated SDK packages

---

## Phase 6 · Metadata Performance & Merge Testing (Week 11‑12)

**Goal**  Validate OMS non‑functional requirements specific to metadata.

**Tasks**

1. **Branch & Merge DAG Stress**
   – 10 k concurrent branches
   – 100 k merge operations
   – Diff generation < 200 ms (P95)
2. **Schema CRUD Latency** < 50 ms
3. **Audit Trail Verification**
   – Ensure append‑only log, immutability proofs

**Deliverables**
Performance reports, optimisation patches, updated CI benchmarks

---

## Tracking & Governance

*Unchanged* — weekly status, RTM table, Git branch strategy, CI/CD quality gates remain identical except for removed cross‑service items.  Requirements formerly labelled **GF‑02/03/04** are re‑tagged **OS‑GF‑xx** (Object Set) or **AS‑GF‑xx** (Action Service) and referenced externally.

---

## Risk Mitigation (Updated)

| Risk                                     | Mitigation                                        |
| ---------------------------------------- | ------------------------------------------------- |
| **Branch DAG explosion**                 | Incremental merge‑queue, DAG compaction algorithm |
| **Semantic/Struct type over‑validation** | Start minimal, release toggles per ADR‑006/007    |
| **Backward compatibility**               | Schema evolution policy, deprecation warnings     |

*“TerminusDB query performance for 1 B+ instances” moved to Object Storage plan.*

---

## Success Criteria

* All metadata requirements ✅ complete
* Test coverage ≥ 95 % (metadata code)
* Branch merge P95 < 200 ms
* Documentation & ADRs up‑to‑date
* External services successfully consume OMS manifests

---

## Next Steps

1. Approve revised scope & phase names
2. Create feature branches (`feature/semantic-types`, …)
3. Begin Phase 1 implementation

**Plan Approved By** \_\_\_\_\_\_\_\_\_\_\_\_\_  **Date** \_\_\_\_\_\_\_\_\_\_\_\_\_  **Target Completion** +12 weeks


---

## Requirement Traceability Matrix (Updated)

| Requirement ID | Status | Implementation File | Test File | Notes |
|----------------|--------|-------------------|-----------|-------|
| FR-OT-CRUD | ✅ Complete | /core/schema/service.py | /tests/test_schema.py | |
| FR-PR-META | ✅ Complete | /models/domain.py | /tests/test_property.py | |
| FR-SH-REUSE | ✅ Complete | /models/domain.py | /tests/test_shared_property.py | |
| FR-LK-DEF | ✅ Complete | /models/domain.py | /tests/test_link_type.py | |
| FR-LK-IDX | ✅ Complete | /core/graph/metadata_generator.py | /tests/test_graph_metadata.py | Metadata only |
| FR-AC-TRX | ✅ Complete | /core/action/service.py | /tests/test_action.py | |
| FR-AC-HIST | ✅ Complete | /core/events/service.py | /tests/test_audit.py | |
| FR-IF-POLY | ✅ Complete | /models/domain.py | /tests/test_interface.py | |
| FR-DT-CONST | ✅ Complete | /models/data_types.py | /tests/test_data_types.py | |
| FR-SM-VALID | ✅ Complete | /models/semantic_types.py | /tests/test_semantic_types.py | Phase 1 |
| FR-ST-STRUCT | ✅ Complete | /models/struct_types.py | /tests/test_struct_types.py | Phase 2 |
| FR-GR-PERM | ✅ Complete | /core/graph/metadata_generator.py | /tests/test_graph_metadata.py | Phase 3-4 |
| GF-02 | ✅ Complete | /core/graph/metadata_generator.py | /tests/test_graph_metadata.py | Index metadata |
| GF-03 | ✅ Complete | /models/domain.py, /core/graph/metadata_generator.py | /tests/test_graph_metadata.py | Propagation rules |
| API-GEN-01 | ✅ Complete | /core/api/schema_generator.py | /tests/test_schema_generator.py | Phase 5 - GraphQL/OpenAPI generation |
| API-GEN-02 | ✅ Complete | /api/v1/schema_generation/endpoints.py | /tests/test_schema_generation_api.py | Phase 5 - API endpoints |
