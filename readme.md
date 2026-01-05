# Mira — Analytics: “Data Sources Live” (What it means + how it’s counted)

## What you’ll see on the Dashboard
Mira’s dashboard has a KPI called **Data sources live**.

It answers:  
> **How many unique data sources are currently being used by live (active) agents?**

Example:
- You have **1 live agent**
- That agent uses **1 website data source**
✅ Then **Data sources live = 1**

---

## What counts as a “data source” in Mira?
A **Data Source** is any knowledge input connected to an agent, such as:
- Website pages / site guidance
- Contact data
- Support FAQs
- Documents / sheets
- Any structured source you’ve added

Mira stores these as “DataSource” records.

---

## How Mira knows which agent is using which source
Instead of directly storing “Agent → DataSource” in one field, Mira uses a **linking record**.

Think of it like:
- Agent (the bot)
- DataSource (the knowledge)
- A “bridge” that connects them

This bridge is stored as **AgentDataSource**, and includes:
- which agent
- which source
- what the source is used for (role)

So Mira can say:
- “Agent A uses Source X for website guidance”
- “Agent A uses Source Y for contact data”
- “Agent B uses Source X for FAQs”

---

## How the “Data Sources Live” number is calculated
Mira counts:
1. Only agents that are **active (live)**
2. All sources linked to those agents
3. Only **unique sources** (deduplicated)

So if:
- One agent has the same source linked in multiple roles  
  ✅ it still counts as **1**
- Two agents use the same source  
  ✅ it still counts as **1 total unique source across live agents**

---

## Why it showed 0 earlier (in simple terms)
The dashboard was trying to count sources by looking for a direct “agent has sources” field.

But Mira actually stores connections in the **AgentDataSource bridge**, not directly on the agent.

So the dashboard was checking the wrong place.

---

## What we changed to fix it
We updated the analytics logic to:
✅ count distinct `DataSource` entries via the `AgentDataSource` bridge  
✅ only count sources used by active agents

---

## How to sanity-check it (non-technical)
If you ever see a mismatch:
- Data sources live is 0
- but you *know* an active bot is using a website source

That usually means:
- the source is being used in chatbot runtime,
- but the “bridge connection” record was not saved properly.

So the fix is:
✅ ensure that whenever you attach a source to an agent, it creates an AgentDataSource link.

---

## Summary
**Data sources live** tells you how much knowledge your live bots are currently using, and Mira computes it by counting the unique sources connected to live agents through the Agent ↔ Source link table.

---
