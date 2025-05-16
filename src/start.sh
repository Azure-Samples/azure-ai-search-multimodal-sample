#!/bin/sh
root=$(pwd)
backendPath="$root/src/backend"
azurePath="$root/.azure"
frontendPath="$root/src/frontend"

# find the .env file in the azurePath directory recursively
envFile=$(find $azurePath -type f -name ".env"| head -n 1)

if [ -f "$envFile" ]; then
    echo ".env file found at: $envFile"
else
    echo ".env file not found. Please run azd up and ensure it completes successfully."
    exit 1
fi

# Load azd environment variables
echo 'Loading azd environment variables'
azdEnv=$(azd env get-values --output json)

# Check if the azd command succeeded
if [ $? -ne 0 ]; then
    echo "Failed to load azd environment variables. Ensure azd is installed and configured correctly."
    exit 1
fi

# Parse and export each environment variable in the current shell session
eval $(echo "$azdEnv" | jq -r 'to_entries | .[] | "export \(.key)=\(.value)"')

echo 'Restore and build frontend'
cd $frontendPath
npm install
npm run build

echo 'Build and start backend'
cd $root

echo 'Creating Python virtual environment'
python3 -m venv .venv

echo 'Installing dependencies from "requirements.txt" into virtual environment (in quiet mode)...'
.venv/bin/python -m pip --quiet --disable-pip-version-check install -r src/backend/requirements.txt

echo 'Starting the app'
.venv/bin/python "src/backend/app.py"