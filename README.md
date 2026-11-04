# Jarvis

A voice assistant Alexa skill backed by Claude (via the Anthropic Messages API), web search (Tavily), and a personal S3-backed wiki the assistant can read from and write to across sessions.

There are two ways to host it:

- **Option A: Alexa-hosted skill (recommended, free).** Amazon runs the Lambda and an S3 bucket for you inside your Alexa developer account. No AWS account or card needed. Python 3.8 only.
- **Option B: your own AWS Lambda.** Full control, Python 3.12, but needs an AWS account (pay-as-you-go).

> **Windows users:** shell commands in this README are bash syntax. Use **Git Bash** or **WSL**, not plain PowerShell — quoting rules differ and the JSON payloads below will fail in PowerShell as-is.

## Prerequisites

- An [Amazon developer account](https://developer.amazon.com/) (for the Alexa skill; can reuse your regular Amazon login)
- A Claude API key from https://platform.claude.com → **API keys**, on an organisation with API credit (**Billing**)
- A [Tavily](https://app.tavily.com/) API key (free tier) for web search
- Python 3.12 locally (for tests and building the upload)

## Setup

1. Clone the repo and `cd jarvis`
2. `pip install -r requirements.txt -r requirements-dev.txt`
3. Copy `.env.example` to `.env` and fill in:
   - `LLM_MODEL` — `claude-haiku-5-5` (recommended) or `claude-sonnet-5-5`
   - `ANTHROPIC_API_KEY` — paste it on **one line**; a key that wrapped onto the next line, or got cut off, fails with `invalid x-api-key`
   - `TAVILY_API_KEY`
   - `S3_BUCKET_NAME` — only for Option B; Alexa-hosted skills use the bucket Alexa provides

### Choosing a model

Alexa abandons a skill turn after about **8 seconds**, so latency matters more than raw capability. Measured locally (simple question / question needing a web search):

| `LLM_MODEL` | Typical time | Notes |
|---|---|---|
| `claude-haiku-5-5` | ~1s / ~2.5–4s | Recommended. Thinking is turned off in `agent.py` |
| `claude-sonnet-5-5` | ~2–7s / ~4–12s | Better answers but too variable for Alexa; thinking set to `between_tools` |

Per-model request settings live in `_MODEL_PARAMS` in `agent.py`. `agent.py` also caps a whole turn at 7 seconds and says "I'm taking too long" instead of letting Alexa time out.

### Where answers come from

- **Weather** uses the `get_weather` tool (`tools/weather.py`), backed by [Open-Meteo](https://open-meteo.com/) (no API key; free for non-commercial use, data under CC BY 4.0). It geocodes the place, then returns the current conditions with the time they apply to, today's high/low and the next 12 hours. Open-Meteo's current values are weather-model estimates for 15-minute intervals, not station measurements, and Jarvis is told to describe them that way. Web search isn't used for weather: in testing, its results mixed current-conditions data with monthly climate pages, and the model extrapolated seasonal ranges into "tonight".
- **Everything else current** (news, prices, scores) uses Tavily via `search_web`.
- The system prompt in `agent.py` only lets the model state values that appear in a tool result, and to say plainly when data is unavailable, stale or not found.
- **What reaches Jarvis**: Alexa only sends slot values, never the full sentence. `utterance_frames.py` defines about 90 intents whose carrier phrase *is* the opening words (`what`, `what's`, `is`, `can`, `explain`, `I`, `my`, `and`, `actually`, ...), so the handler rebuilds the user's words exactly ("I prefer tea" → `IStatementIntent` + "prefer tea"). The interaction model JSON is generated from it: edit `utterance_frames.py`, run `python scripts/build_interaction_model.py`, paste `skill-package/interactionModels/custom/en-US.json` into the console's JSON Editor and **Build skill**. `tests/test_interaction_model.py` checks the JSON against Amazon's SearchQuery and sample rules.
- **Memory**: only explicit requests ("remember that …", "note that …", "save that …") are saved, immediately, to `wiki/user/profile.md`. Jarvis says it was saved only if the write succeeded. Other personal statements are conversation context only. Saved notes are given to the model on every turn.
- Every tool call and a preview of its result is logged (`tool <name> <input> -> <result>`), so CloudWatch shows exactly what an answer was based on.

## Running tests

```bash
pytest
```

## Option A: Alexa-hosted skill (recommended)

Why the code looks the way it does: Alexa-hosted skills run **Python 3.8** and install `requirements.txt` themselves. Deploys that included litellm or the `anthropic` SDK left the hosted Lambda without our code (`No module named 'lambda_function'`). Their compiled dependencies (pydantic-core, jiter, tokenizers) are the suspected cause, but the hosted build log was never retrieved, so that isn't confirmed. What is established: with `requirements.txt` kept **pure Python** and `agent.py` calling the Claude API with `requests`, the package deploys and runs. Hosted skills also can't have Lambda environment variables edited, so the API keys ship inside the upload as `lambda/jarvis.env` (loaded by `config.py`), and the wiki uses the bucket Alexa provides (`S3_PERSISTENCE_BUCKET`).

### First-time setup

1. Go to https://developer.amazon.com/alexa/console/ask → **Create Skill**:
   - Name `Jarvis`, locale **English (US)**
   - Type **Other** → **Custom**
   - Hosting **Alexa-hosted (Python)**, region **EU (Ireland)** (or nearest to you)
   - Template **Start from Scratch** → **Create Skill**

   Already have a Jarvis skill pointing at an old Lambda? Instead of creating a new one, use the console's **Convert to Alexa-hosted** (Python, same region) on it. Don't keep two skills with the invocation name "jarvis" in testing at once.
2. **Build → Interaction Model → JSON Editor**: paste the contents of `skill-package/interactionModels/custom/en-US.json`, **Save**, then **Build skill**.

### Deploying code

1. Build the upload (refuses to run while `.env` still has placeholder values):
   ```bash
   python scripts/build_hosted.py
   ```
   This writes `dist/alexa-hosted-code.zip` (gitignored — **it contains your API keys**; don't share it).
2. In the skill's **Code** tab → **Import Code** → choose `dist/alexa-hosted-code.zip` → select all files and confirm overwrites. Amazon's starter `utils.py` can stay; it's unused.
3. Click **Deploy** and wait for **Last Deployed: …** to update. The first build takes a few minutes.
4. **Test** tab → set to **Development** → type `open jarvis`, then `ask jarvis what's the weather in Berlin`.

Repeat steps 1–3 after any code or key change.

Free usage limits (per developer account): unlimited Lambda requests, 25 GB S3. See [Alexa-hosted usage limits](https://developer.amazon.com/en-US/docs/alexa/hosted-skills/usage-limits.html).

## Option B: your own AWS Lambda

### First time with AWS? Start here

1. **Create an AWS account** — go to https://aws.amazon.com/, click "Create an AWS Account", follow signup (needs email, phone, credit card). If you've had an AWS account before, the free plan isn't offered and you'll be on pay-as-you-go; this project's usage is tiny, but set an AWS Budget alert. Free-plan accounts are **closed** when the plan ends unless upgraded, which takes the Lambda down with them.
2. **Install Node.js** (needed for the ASK CLI) — https://nodejs.org/ (LTS version). Verify: `node --version`.
3. **Install the AWS CLI** — https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html (pick your OS). Verify: `aws --version`.
4. **Create an AWS access key**:
   - AWS Console → click your account name (top right) → "Security credentials"
   - Under "Access keys" → "Create access key" → choose "Command Line Interface (CLI)" → confirm
   - Copy the Access Key ID and Secret Access Key (shown once)
5. **Configure the CLI** with those keys:
   ```bash
   aws configure
   # AWS Access Key ID: <paste>
   # AWS Secret Access Key: <paste>
   # Default region: eu-central-1   (or your preferred region — keep it consistent everywhere below)
   # Default output format: json
   ```
   Verify it worked:
   ```bash
   aws sts get-caller-identity
   ```
   This should print your AWS account ID/user ARN. If it errors, the keys from step 4 weren't entered correctly — rerun `aws configure`.

### Provisioning AWS resources

Do this once, before the first deploy. Replace `eu-central-1` if you changed `REGION` in `scripts/deploy.py`/`deploy.sh`.

1. **Create the S3 bucket** (must match `S3_BUCKET_NAME` in `.env`; bucket names are global, so pick a unique one if `jarvis-wiki` is taken):
   ```bash
   aws s3 mb s3://jarvis-wiki --region eu-central-1
   ```

2. **Create an IAM role for Lambda** with basic execution + S3 read/write:
   ```bash
   aws iam create-role --role-name jarvis-lambda-role \
     --assume-role-policy-document '{
       "Version": "2012-10-17",
       "Statement": [{"Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"}, "Action": "sts:AssumeRole"}]
     }'

   aws iam attach-role-policy --role-name jarvis-lambda-role \
     --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole

   aws iam put-role-policy --role-name jarvis-lambda-role \
     --policy-name jarvis-s3-access \
     --policy-document '{
       "Version": "2012-10-17",
       "Statement": [{
         "Effect": "Allow",
         "Action": ["s3:GetObject", "s3:PutObject"],
         "Resource": "arn:aws:s3:::jarvis-wiki/*"
       }]
     }'
   ```
   Wait ~10s for IAM role propagation before the next step.

3. **Create the Lambda function** (first deploy needs an initial zip — an empty placeholder works, `deploy.py` overwrites it). `zip` is built into Git Bash/WSL/macOS/Linux; on plain Windows install it via `winget install GnuWin32.Zip` or just use Git Bash, which ships with `zip`:
   ```bash
   mkdir -p package && cd package && zip -r ../lambda.zip . -x '.*' && cd ..
   ROLE_ARN=$(aws iam get-role --role-name jarvis-lambda-role --query 'Role.Arn' --output text)

   aws lambda create-function \
     --function-name jarvis \
     --runtime python3.12 \
     --handler lambda_function.lambda_handler \
     --role "$ROLE_ARN" \
     --timeout 30 \
     --memory-size 256 \
     --zip-file fileb://lambda.zip \
     --region eu-central-1
   ```

4. **Set the function's environment variables** — same 4 values you put in `.env`. Two ways:

   **Console (easier for first time):**
   - Go to https://console.aws.amazon.com/lambda → click function `jarvis`
   - Tab "Configuration" → side menu "Environment variables" → "Edit"
   - "Add environment variable", repeat for each:
     - `LLM_MODEL` = `claude-haiku-5-5`
     - `ANTHROPIC_API_KEY` = your Claude API key
     - `TAVILY_API_KEY` = your Tavily key
     - `S3_BUCKET_NAME` = `jarvis-wiki`
   - Click "Save"

   **CLI (one shot):**
   ```bash
   aws lambda update-function-configuration \
     --function-name jarvis \
     --region eu-central-1 \
     --environment "Variables={LLM_MODEL=claude-haiku-5-5,ANTHROPIC_API_KEY=your-key,TAVILY_API_KEY=your-key,S3_BUCKET_NAME=jarvis-wiki}"
   ```

5. **Note the function ARN** — you'll need it for `skill.json`:
   ```bash
   aws lambda get-function --function-name jarvis --region eu-central-1 --query 'Configuration.FunctionArn' --output text
   ```

Now run the real deploy to push actual source code:
```bash
python scripts/deploy.py
# or
bash scripts/deploy.sh
```
Both install dependencies into `package/`, zip the source into `lambda.zip`, and `update-function-code` on the `jarvis` function (set `REGION`/`FUNCTION_NAME` at the top of the script if yours differ).

### Setting up the Alexa skill (Option B)

1. Install the [ASK CLI](https://developer.amazon.com/en-US/docs/alexa/smapi/quick-start-alexa-skills-kit-command-line-interface.html) (`npm install -g ask-cli`, then `ask configure`) or use the [Alexa developer console](https://developer.amazon.com/alexa/console/ask).
2. In `skill-package/skill.json`, replace `REPLACE_WITH_LAMBDA_ARN` with the ARN from step 5 above.
3. Create the skill:
   - **CLI:** `ask deploy` from the repo root (reads `skill-package/`).
   - **Console:** create a new custom skill, then import the manifest (`skill-package/skill.json`) and interaction model (`skill-package/interactionModels/custom/en-US.json`) under Build → JSON Editor / Interaction Model.
4. **Grant the Alexa service permission to invoke your Lambda** — required, easy to miss, causes silent "there was a problem" errors in the simulator if skipped:
   ```bash
   aws lambda add-permission \
     --function-name jarvis \
     --statement-id alexa-skill-trigger \
     --action lambda:InvokeFunction \
     --principal alexa-appkit.amazon.com \
     --region eu-central-1
   ```
5. Build the interaction model in the console (Build tab → Build Model), then test in the simulator: "Alexa, open Jarvis".

## Troubleshooting

Any unhandled error in the skill is now logged and spoken as "I ran into a problem. Please try again." If you instead get Alexa's generic "there was a problem with the requested skill's response", the Lambda didn't run your code at all.

1. **Check the account first.** If the skill stopped working with no code change, make sure the hosting account still exists: for Option B, the AWS console shows "Your account is closed" or a billing banner; local `aws` commands fail with `UnrecognizedClientException`.
2. **Read the logs.**
   - Option A: **Code** tab → **CloudWatch Logs** (pick your hosting region from the ▾ menu). The first page is a sign-in redirect; wait for it to load. If it never does, try a normal Chrome window with third-party cookies allowed for `aws.amazon.com` and extensions off.
   - Option B:
     ```bash
     aws logs tail /aws/lambda/jarvis --follow --region eu-central-1
     ```
     Trigger the skill again in the simulator while this is running and watch the output.
3. **`Runtime.ImportModuleError: No module named 'lambda_function'`** (Option A) → the deploy never put your code on the Lambda; the deploy itself failed. Get the build error from the deploy's **View** link (CloudWatch). For this project it happened with compiled dependencies in `requirements.txt` and stopped once they were removed, so keep `requirements.txt` pure Python.
4. **`ImportModuleError` naming another module** (Option B) → dependencies weren't installed for Lambda's Linux runtime. Re-run `python scripts/deploy.py` (it installs with `--platform manylinux2014_x86_64`); don't `pip install` locally and zip that up directly on Windows/macOS.
5. **`invalid x-api-key`** → the key in `.env`/`jarvis.env` is incomplete or wrapped onto a second line; re-copy it with the console's Copy button. **`credit balance is too low`** → the key is valid but its organisation has no API credit; check **Billing** on platform.claude.com for the same organisation.
6. **"I'm taking too long to answer that"** → a turn hit the 7-second cap; usually a slow web search or a slower model. Prefer `claude-haiku-5-5`.
7. **"AccessDenied" on S3 calls** (Option B) → IAM role policy from Provisioning step 2 didn't attach, or bucket name mismatch between `.env`/Lambda env vars and the actual bucket.
8. **"there was a problem..." with no Lambda log entry at all** (Option B) → the invoke permission (Alexa skill setup step 4) is missing or wrong `--principal`/region.
