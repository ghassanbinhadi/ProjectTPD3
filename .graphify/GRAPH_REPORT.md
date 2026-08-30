# Graph Report - .  (2026-08-30)

## Corpus Check
- Corpus is ~19,525 words - fits in a single context window. You may not need a graph.

## Summary
- 61 nodes · 68 edges · 10 communities detected
- Extraction: 84% EXTRACTED · 16% INFERRED · 0% AMBIGUOUS · INFERRED: 11 edges (avg confidence: 0.82)
- Token cost: 0 input · 0 output
- Edge kinds: contains: 37 · references: 14 · calls: 5 · conceptually_related_to: 5 · shares_data_with: 4 · affiliated_with: 1 · implements: 1 · semantically_similar_to: 1


## Input Scope
- Requested: auto
- Resolved: committed (source: default-auto)
- Included files: 11 · Candidates: 24
- Excluded: 0 untracked · 3909 ignored · 0 sensitive · 1 missing committed
- Recommendation: Use --scope all or graphify.yaml inputs.corpus for a knowledge-base folder.

## Graph Freshness
- Built from Git commit: `079e1bc`
- Compare this hash to `git rev-parse HEAD` before trusting freshness-sensitive graph output.
## God Nodes (most connected - your core abstractions)
1. `Graphify Pipeline` - 8 edges
2. `Team Section` - 7 edges
3. `Results Charts Section` - 6 edges
4. `Direction Toggle` - 5 edges
5. `loadCase()` - 4 edges
6. `Hero Section` - 4 edges
7. `Community Detection` - 3 edges
8. `Hero WebGL Scene` - 3 edges
9. `KAUST Academy` - 3 edges
10. `rnd()` - 2 edges

## Surprising Connections (you probably didn't know these)
- `Graphify Knowledge Graph` --conceptually_related_to--> `PeerGPT Project`  [INFERRED]
  CLAUDE.md → README.md
- `CLAUDE.md Configuration` --references--> `Graphify Skill`  [EXTRACTED]
  .claude/CLAUDE.md → .claude/skills/graphify/SKILL.md

## Hyperedges (group relationships)
- **Graphify Core Value Propositions** — graph_persistent_graph, graph_audit_trail, graph_community_detection [EXTRACTED 1.00]
- **Graphify Extraction Pipeline (AST + Semantic)** — graph_ast_extraction, graph_semantic_extraction, graphify_pipeline [EXTRACTED 1.00]
- **Graphify Output Formats** — graph_html_output, graph_obsidian_vault, graph_neo4j_export, graph_mcp_server [EXTRACTED 1.00]
- **Results Chart Suite** — index_chart_benefit_per_revision, index_chart_correction_effectiveness, index_chart_false_alarm, index_chart_ablation [EXTRACTED 0.90]
- **Direction Asymmetry Display** — index_direction_toggle, index_hero_scene, index_outcome_toggle, index_results [INFERRED 0.80]
- **Pipeline Stages** — index_pipeline_svg, index_method [EXTRACTED 0.95]

## Communities

### Community 0 - "Site Structure & Sections"
Cohesion: 0.22
Nodes (10): CLAUDE.md Configuration, AST Structural Extraction, PDF OCR Preflight, HTML Interactive Graph, Neo4j Export, Obsidian Vault Output, Semantic Extraction, Graphify Tool (+2 more)

### Community 1 - "Results Charts & Direction"
Cohesion: 0.20
Nodes (7): Graphify Knowledge Graph, Background Section, Decision Policy Section, Demo Stepper Section, Method Pipeline Section, Pipeline SVG Diagram, PeerGPT Project

### Community 2 - "Team & Authors"
Cohesion: 0.27
Nodes (10): 3-Way Feature Ablation Chart, Benefit per Revision Chart, Correction Effectiveness Chart, False Alarm Rate Chart, Llama-solver Qwen-critic Direction, Qwen-solver Llama-critic Direction, Direction Toggle, Hero WebGL Scene (+2 more)

### Community 3 - "Graphify Extraction Pipeline"
Cohesion: 0.29
Nodes (7): activate(), driveScene(), loadCase(), outcomeHint, render(), renderQuestion(), renderSteps()

### Community 4 - "Graphify Tooling"
Cohesion: 0.29
Nodes (8): Abdullah Asiri, Dr. Eman Alnabati, Farah Alshammari, Ghassan Alqahtani, Hero Section, Team Section, KAUST Academy, Lama Alshammari

### Community 5 - "3D Scene Rendering"
Cohesion: 0.33
Nodes (2): buildCluster(), rnd()

### Community 6 - "Graph Value Propositions"
Cohesion: 1.00
Nodes (3): Honest Audit Trail, Community Detection, Persistent Graph

### Community 7 - "Interactivity Logic"
Cohesion: 1.00
Nodes (1): Graphify MCP Server

### Community 8 - "Search Question Paper"
Cohesion: 1.00
Nodes (1): When Should an LLM Listen to Another LLM?

### Community 9 - "Roll Dice Utility"
Cohesion: 1.00
Nodes (1): Roll Dice Skill

## Knowledge Gaps
- **18 isolated node(s):** `outcomeHint`, `CLAUDE.md Configuration`, `Roll Dice Skill`, `Graphify MCP Server`, `Neo4j Export` (+13 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `3D Scene Rendering`** (2 nodes): `buildCluster()`, `rnd()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Interactivity Logic`** (1 nodes): `Graphify MCP Server`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Search Question Paper`** (1 nodes): `When Should an LLM Listen to Another LLM?`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Roll Dice Utility`** (1 nodes): `Roll Dice Skill`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Team Section` connect `Graphify Tooling` to `Results Charts & Direction`?**
  _High betweenness centrality (0.068) - this node is a cross-community bridge._
- **Why does `Results Charts Section` connect `Team & Authors` to `Results Charts & Direction`?**
  _High betweenness centrality (0.060) - this node is a cross-community bridge._
- **Why does `Hero Section` connect `Graphify Tooling` to `Team & Authors`, `Results Charts & Direction`?**
  _High betweenness centrality (0.044) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `Direction Toggle` (e.g. with `3-Way Feature Ablation Chart` and `Hero WebGL Scene`) actually correct?**
  _`Direction Toggle` has 2 INFERRED edges - model-reasoned connections that need verification._
- **What connects `outcomeHint`, `CLAUDE.md Configuration`, `Roll Dice Skill` to the rest of the system?**
  _18 weakly-connected nodes found - possible documentation gaps or missing edges._