# Jarvis

A voice assistant Alexa skill backed by a swappable LLM (via [litellm](https://docs.litellm.ai/)), web search, and a personal S3-backed wiki the assistant can read from and write to across sessions.

## Prerequisites

- AWS account (Lambda + S3)
- Amazon Alexa developer account
- An API key for an LLM provider supported by litellm (Groq, OpenAI, Anthropic, Gemini, ...)
- A [Tavily](https://tavily.com) API key (used for web search)
- Python 3.12, AWS CLI configured (`aws configure`)

## Setup

1. Clone the repo and `cd jarvis`
2. `pip install -r requirements.txt -r requirements-dev.txt`
3. Copy `.env.example` to `.env` and fill in:
   - `LLM_MODEL` — provider/model string, e.g. `groq/openai/gpt-oss-20b` (see table below)
   - the matching provider API key env var
   - `TAVILY_API_KEY`
   - `S3_BUCKET_NAME` — S3 bucket used to store the per-user wiki

## Choosing a provider

`LLM_MODEL` uses litellm's `provider/model` naming. litellm reads the matching API key env var automatically based on the prefix:

| `LLM_MODEL` example | Required env var |
|---|---|
| `groq/openai/gpt-oss-20b` | `GROQ_API_KEY` |
| `openai/gpt-4o-mini` | `OPENAI_API_KEY` |
| `anthropic/claude-sonnet-4-6` | `ANTHROPIC_API_KEY` |
| `gemini/gemini-2.0-flash` | `GEMINI_API_KEY` |

Full provider list: https://docs.litellm.ai/docs/providers. Pick a model that supports tool/function calling — Jarvis relies on it for web search and wiki lookups.

## Running tests

```bash
pytest
```

## Provisioning AWS resources

Do this once, before the first deploy. Replace `eu-central-1` if you changed `REGION` in `scripts/deploy.py`/`deploy.sh`.

1. **Create the S3 bucket** (must match `S3_BUCKET_NAME` in `.env`):
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

3. **Create the Lambda function** (first deploy needs an initial zip — an empty placeholder works, `deploy.py` overwrites it):
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

4. **Set the function's environment variables** (console: Lambda → Configuration → Environment variables, or CLI):
   ```bash
   aws lambda update-function-configuration \
     --function-name jarvis \
     --region eu-central-1 \
     --environment "Variables={LLM_MODEL=groq/openai/gpt-oss-20b,GROQ_API_KEY=your-key,TAVILY_API_KEY=your-key,S3_BUCKET_NAME=jarvis-wiki}"
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

## Setting up the Alexa skill

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
