#!/bin/bash
# Deploy the Jarvis Lambda function.
# Usage: bash scripts/deploy.sh
#
# Prerequisites:
#   - AWS CLI configured (aws configure)
#   - Lambda function already created in AWS console named "jarvis"
#   - Set REGION below to your AWS region (e.g. eu-central-1)

set -e

if [ ! -f "lambda_function.py" ]; then
  echo "Error: run this script from the jarvis/ directory (cd jarvis && bash scripts/deploy.sh)"
  exit 1
fi

FUNCTION_NAME="jarvis"
REGION="eu-central-1"   # <-- change to your region

echo "==> Cleaning previous build..."
rm -rf package/ lambda.zip

echo "==> Installing dependencies into package/..."
pip install -r requirements.txt -t package/ --quiet

echo "==> Copying source files..."
cp lambda_function.py intent_handlers.py agent.py config.py wiki_manager.py ssml_builder.py package/
cp -r tools/ package/tools/

echo "==> Creating lambda.zip..."
cd package && zip -r ../lambda.zip . -q && cd ..

echo "==> Uploading to Lambda (function: $FUNCTION_NAME, region: $REGION)..."
aws lambda update-function-code \
  --function-name "$FUNCTION_NAME" \
  --zip-file fileb://lambda.zip \
  --region "$REGION" \
  --output text

echo ""
echo "Done! Lambda function updated."
echo "Check the Alexa Developer Console to test with the simulator."
