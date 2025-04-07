# LARC2 - Lexicon M300L Web Controller Development Plan

## Overall Goal

Implement a fully functional web interface (React frontend, Python backend) to control the Lexicon M300L, mirroring the capabilities described in the owner's manual and the existing `frontend/ARCHITECTURE.md`.

## High-Level Plan

1.  **Phase 1: Foundation & Core Communication**
    *   Solidify backend MIDI connection (`rtmidi`) and basic SysEx/NRPN message generation/parsing.
    *   Implement robust WebSocket communication for status and parameter updates.
    *   Refine frontend MIDI port selection and connection status display.
    *   Implement basic parameter display/editing UI for *one* core algorithm (e.g., Random Hall) to validate the end-to-end communication flow.

2.  **Phase 2: Setup & Effect Management**
    *   Implement backend logic for requesting, parsing, and storing Setup and Effect presets/registers (Bulk SysEx dumps).
    *   Develop frontend UI (Preset Sidebar, Preset Manager View) for browsing, searching, loading, and saving Setups and Effects, using the provided preset list (`M300_V3_PRESETS`).

3.  **Phase 3: Full Parameter Control & Algorithm Expansion**
    *   Systematically implement UI controls (knobs, sliders, toggles) for *all* parameters of *all* M300L algorithms based on the manual (Chapter 4).
    *   Ensure the backend correctly maps UI changes to the corresponding SysEx or NRPN messages.

4.  **Phase 4: Advanced Features**
    *   **Modulation Matrix:** Complete the `ModulationMatrixView` UI and backend logic (Manual Ch 7).
    *   **Time Code Automation:** Implement UI and backend logic for the Time Code Event List (Manual Ch 6).
    *   **System Control:** Create UI elements for M300L's Control Mode pages (Manual Ch 3).

5.  **Phase 5: Refinement, Testing & Documentation**
    *   Align frontend structure with `frontend/ARCHITECTURE.md`.
    *   Implement responsive design, keyboard shortcuts, error boundaries, etc.
    *   Add unit and integration tests.
    *   Update/create documentation.

## System Interaction Diagram

```mermaid
graph LR
    A[Frontend UI (React)] -- WebSocket --> B(WebSocket Server (Python));
    B -- Python Calls --> C{M300Controller (Python)};
    C -- rtmidi --> D[MIDI Interface];
    D -- MIDI Cable --> E(Lexicon M300L Hardware);
    E -- MIDI Cable --> D;
    D -- rtmidi --> C;
    C -- WebSocket Updates --> B;
    B -- WebSocket --> A;

    subgraph User's Computer
        A
        B
        C
        D
    end

    subgraph External Hardware
        E
    end