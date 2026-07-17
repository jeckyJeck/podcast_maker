purpose:
in the prompt lab we want to create system to improve the prompts used in the podcast creator.
we have backend that gets YAML as descibed in PIPELINE_CONTRACT.md
and runs it and returns the results.

We have optimization_agent folder which will contain code for autonomus LLM agent with tools that enables it to read past pipelines and create new YAML for the backend to run.

We have front end that give the user a. the ability to create and run new pipeline yaml file b. interface to control the agent (not implemented yet).

In the future we want to add evaluation process.



current folder structure:

prompts_lab/
├── common_resources/           <-- התיקייה המשותפת החדשה
│   ├── PIPELINE_CONTRACT.md    <-- חוזה ה-YAML המשותף
│   ├── templates/              <-- נקודות מוצא/טמפלייטים המכילים pipeline.yaml ופלט דיפולטיבי
│   │   ├── duo_long/
│   │   └── solo_short/
│   └── experiments_runs/       <-- הרצות היסטוריות של הסוכן והבקאנד (מוחרג ב-.gitignore)
├── lab_backend/                <-- קוד הבקאנד של המעבדה
├── optimization_agent/         <-- קוד סוכן האופטימיזציה
├── front_client/               <-- UI client for humen use 
├── front_client_old/           <-- old front client (will be deleted)
└── requirements.txt
