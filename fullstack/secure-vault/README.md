# SecureVault-Dashboard

This challenge is designed to test your ability to bridge Computer Science fundamentals with Modern Frontend Engineering.

## 1. Business Scenario & Context

**Client:** SecureVault Inc.
**Industry:** Enterprise Cloud Security

**The Problem:** SecureVault offers high-security cloud storage for law firms and banks. Their backend engineers have built a robust API that returns folder structures efficiently. However, their current frontend is a simple list that is hard to navigate. Clients are complaining that they can't manage nested files easily.

**Your Role:** You are the incoming Junior Frontend Engineer. Your task is to design and build a modern, high-performance "File Explorer" UI that impresses the CTO and the Design Lead.

---

## 2. The Assignment Stages

This is a **hybrid design/engineering challenge**. You are expected to demonstrate competence in both visual design logic and algorithmic frontend implementation.

### Phase 1: The Design System

**Before writing code, you must design the interface.**

- **Deliverable:** A link to a design file (Figma, Penpot, or Sketch) or a PDF export of your design frames.
- **Requirement:** Your design file must include a dedicated **"Design System" page** that defines:
  - **Typography Scale**
  - **Color Palette**
  - **Spacing Grid**
  - **Component States**
- **Brand Guidelines:** SecureVault wants a "Dark Mode" aesthetic that feels "cyber-secure, precise, and fast."

### Phase 2: The Implementation

**Build the application using the design system you created in Phase 1.**

- **Constraint:** You **cannot** use component libraries like Bootstrap, Material UI, Chakra UI, or Ant Design. You must build your components from scratch to prove you understand CSS layout and component abstraction.
- **Note:** CSS frameworks like Tailwind are allowed _only_ if you use them to build your own reusable component architecture.

---

## 3. User Stories & Acceptance Criteria

### Core Features (Required)

#### Story 1: The Recursive Tree

> "As a lawyer with 10 years of case files, I need to navigate deeply nested folders without reloading the page."

- **AC 1:** The UI renders the folder structure from the provided JSON.
- **AC 2:** The component structure must be **recursive**. It should handle 2 levels of depth or 20 levels without breaking the UI.
- **AC 3:** Folders must expand/collapse on click.

#### Story 2: File Details & Inspection

> "As a user, I need to see file metadata to ensure I'm opening the right version."

- **AC 1:** Clicking a file "selects" it (distinct visual state based on your design).
- **AC 2:** A "Properties Panel" displays the selected file's Name, Type, and Size.

#### Story 3: Keyboard Accessibility

> "As a power user, I hate reaching for my mouse. I want to navigate the vault using only my keyboard."

- **AC 1:** `Up/Down` arrows move focus between the visible items in the explorer.
- **AC 2:** `Right` arrow expands a folder; `Left` arrow collapses it.
- **AC 3:** `Enter` selects the file.

### The "Wildcard" Feature (Required)

#### Story 4: The Innovation Clause

> "As a developer, I want to add one feature that the client didn't ask for, but would significantly improve the user experience."

- **Task:** Identify a gap in the requirements. What is missing?
- **AC 1:** Implement **one** additional feature of your choice.
- **AC 2:** In your README, explain _why_ you chose this feature and how it adds value to the business.

### Bonus Feature (Optional)

#### Story 5: Search & Filter

- **AC 1:** A search bar filters the view. Matching items deep inside folders should force those folders to expand automatically.

---

## 4. Technical Requirements

- **Data:** Use the `data.json` file provided in this repo. Do not edit the JSON structure, but you may add more items to test performance.
- **Tech Stack:** React, Vue, Svelte, or Vanilla JS.
- **Documentation:** Your README in the submission must include:
  1.  Setup instructions.
  2.  Link to your Design File.
  3.  Explanation of your **Recursive Strategy** (how you managed the data structure).
  4.  Explanation of your **Wildcard Feature**.

---

## 5. Submission Instructions

1.  **Fork** this repository.
2.  Complete the code in your fork.
3.  **Update the README:**
    - **Delete** all the instructions in this file (the text you are reading now).
    - **Replace** them with your own documentation as outlined in Section 4.
    - _Note: Do not append your docs to the end. The final README should look like a professional project documentation, not a homework assignment._
4.  Submit your repo link via the [online](https://forms.cloud.microsoft/e/PrfSgKKQ0k) form.

---

### ⚠️ CRITICAL: Pre-Submission Checklist

**STOP and review your work.** To be eligible for the Solution Defense interview, your submission **MUST** pass the following "Gatekeeper" checks.

If any of the following are incorrect, your submission will be flagged as incomplete and you will **NOT** be invited for an interview.

1.  **Public Repository:** Is your GitHub repository set to **Public**? (Private links will be auto-rejected).
2.  **Audit-Ready History:** Does your Git commit history show your progress over time? (Repositories with a single "Initial Commit" or "Upload files" containing the entire project will be **rejected as unverifiable**).
3.  **Working Deployment:** Have you tested your live link in an **Incognito/Private** window to ensure it loads without errors?
4.  **No Restricted Libraries:** Did you build your own components? (Submissions using **Bootstrap, Material UI, or Chakra UI** will be disqualified).
5.  **Design File Access:** Is your Figma/Penpot link included and set to **"Anyone with the link can view"**?
6.  **Documentation:** Have you deleted the original assignment text from the `README.md` and replaced it with your own project documentation?

> **By submitting your work, you acknowledge that failure to meet these criteria effectively ends your application process.**
