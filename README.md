# Stop inactive Azure Virtual Machines automatically

The app automatically stops(deallocates) Azure Virtual Machines if they are inactive for a while. Before stopping the VM, a warning email notification will be send. You have the flexibility to define:

1. Which VMs are in the scope of the app. This can be done at the resource group level or VM level.
2. Period of inactivity.
3. Email to which the notification is to be sent.

## How it works

## Deploying to Azure

### Pre-requisites

- #### Azure CLI

  If you don't have Azure CLI, install it following instructions in here : https://docs.microsoft.com/en-us/cli/azure/install-azure-cli?view=azure-cli-latest.

- #### Azure Function tools

  Azure function tools is required for deploying the function app code. You will find the instructions for installing it here: https://docs.microsoft.com/en-us/azure/azure-functions/functions-run-local?tabs=windows#v2

- #### Azure SendGrid Account

  App uses SendGrid to send warning email before stopping VMs. Create an Azure SendGrid account following instructions in here : https://docs.microsoft.com/en-us/azure/sendgrid-dotnet-how-to-send-email#create-a-sendgrid-account. Note the SendGrid API key, you will need it while deploying the function app.

- #### This repo

  Clone this repo. You will find the ARM templates for deploying the function app and associated storage account, application insights etc. in the `Azure` folder. Move to it and execute the following commands for deploying the app.

### Deployment Instructions

1. Create custom role for the function app.

   ```sh
   az role definition create --role-definition ./vmautostop-custom-role.json
   ```

2. Create resource group for deploying the function app, storage account and application insights.

   ```sh
   az group create --name <Resource group name> --location <Location>
   ```

   example:

   ```sh
   az group create --name rg-vmautostop --location WestUS
   ```

3. Create the function app, storage account and application insights.

   ```sh
   az group deployment create --resource-group <Resource group name> \
      --template-file vmautostop-func-dedicated.json \
      --parameters '{ "sendGridApiKey": {"value": "<SendGrid api key>"},
                     "warningEmailFrom": {"value": "<From email id for sending warning email>"},
                     "warningEmailTo" :{"value": "<To email id for sending warning email>"}}'
   ```

   example:

   ```sh
   az group deployment create --resource-group rg-vmautostop \
      --template-file vmautostop-func-dedicated.json \
      --parameters '{ "sendGridApiKey": {"value": "SG.XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"},
                     "warningEmailFrom": {"value": "vmautostop@gmail.com"},
                     "warningEmailTo" :{"value": "John.Doe@gmail.com"}}'
   ```

4. Get the service principle id of the function app.

   ```sh
   az functionapp show --name <Function app name> \
      --resource-group <Resource group name> \
      --query 'identity.principalId'
   ```

   example:

   ```sh
   az functionapp show --name fn-vmautostop-kjfmr2d6ddosw \
      --resource-group rg-vmautostop \
      --query 'identity.principalId'
   ```

5. Assign the custom role to the function app.

   ```sh
   az role assignment create --assignee <Service principle id> \
        --role "Virtual Machine Auto Stop" \
        --subscription <Subscription id>
   ```

   example:

   ```sh
   az role assignment create --assignee "ec359a23-0de2-47d6-a45d-67922448061a" \
     --role "Virtual Machine Auto Stop" \
     --subscription "3af84b10-189c-40a6-b66c-2905fcc0ea9d"
   ```

6. Build and publish the function app.

   ```sh
   func azure functionapp publish <Function app name> --build remote
   ```

   example:

   ```sh
   func azure functionapp publish fn-vmautostop-kjfmr2d6ddosw --build remote
   ```

### Configuration
