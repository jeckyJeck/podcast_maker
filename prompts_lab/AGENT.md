purpose:
in the prompt lab we want to create system to improve the prompts used in the podcast creator.
we have backend that gets YAML as descibed in PIPELINE_CONTRACT.md
and runs it and returns the results.

We have optimization_agent folder which will contain code for autonomus LLM agent with tools that enables it to read past pipelines and create new YAML for the backend to run.

We have front end that give the user a. the ability to create and run new pipeline yaml file b. interface to control the agent (not implemented yet).

In the future we want to add evaluation process.



current folder structure:

prompts_lab/
├── optimization_agent/         <-- optimization agent code (talks to the backend over HTTP)
└── front_client/               <-- UI client for human use

There is no lab backend: the lab uses the main backend (backend/) under /prompts-test-api.
The YAML contract, pipelines, schemas, rubrics and run data live in backend/resources and backend/data
(see backend/resources/PIPELINE_CONTRACT.md).
