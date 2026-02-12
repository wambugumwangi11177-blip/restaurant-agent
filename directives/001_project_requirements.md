# Project Requirements: Restaurant Agent

> Migrated from original GEMINI.md

## Core Philosophy
This project is an AI Infrastructure App for Restaurants. It must be:
1.  **Scalable**: Multi-tenant architecture (Main Account -> Sub-accounts).
2.  **Premium**: "God-Tier" UI/UX. Dark mode, glassmorphism, fluid animations.
3.  **Intelligent**: AI agents embedded in every module.

## Tech Stack Rules
-   **Frontend**: Next.js (App Router), TailwindCSS.
-   **Backend**: Python (FastAPI).
-   **Database**: Neon (PostgreSQL).
-   **Hosting**: Vercel (FE), Render (BE).

## Modules
1.  **POS (Point of Sale)**: Fast, touch-friendly, offline-capable logic.
2.  **KDS (Kitchen Display System)**: Real-time syncing, station routing.
3.  **Inventory**: Real-time deduction, predictive ordering (AI).
4.  **Reservations**: Visual table management, SMS/WhatsApp integration.

## AI Infrastructure
-   Centralized AI Agent handling specific tasks across modules.
-   Data-driven insights for restaurants.
