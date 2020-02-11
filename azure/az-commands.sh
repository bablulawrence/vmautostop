az role definition create --role-definition ./vmautostop-role.json

az group create --name rg-vmautostop --location WestUS

az group deployment create --resource-group rg-vmautostop \
    --template-file vmautostop-func-dedicated.json \
    --parameters '{ "sendGridApiKey": {"value": "yourSgkey"}, 
                    "warningEmailFrom": {"value": "vmautostop@youremail.com"}, 
                    "warningEmailTo" :{"value": "John.Doe@youremail.com"}}'

az functionapp show --name "<function app name>" --resource-group "<resource group name>" --query 'identity.principalId'

az role assignment create --assignee "<service principle id>" \
     --role "Virtual Machine Auto Stop" \
     --subscription "<subscription id>"
func azure functionapp publish "<function app name>" --build remote 
