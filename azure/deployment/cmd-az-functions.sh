mkdir vmautostop
cd vmautostop
mkdir azure
python3.7 -m venv env
pip install -r requirements.txt
az group create --name rg-vmautostop --location southeastasia
az storage account create --name stgvmautostop --resource-group rg-vmautostop

az deployment create --location WestUS --template-file azuredeploy.json  \
            --parameters @params.json --parameters https://mysite/params.json --parameters
        MyValue=This MyArray=@array.json
        
az deployment create --template-file func-consumption.json --parameters @func-consumption.parameters.json 

az functionapp create --name fn-vmautostop --resource-group rg-vmautostop \
    --consumption-plan-location southeastasia \
    --os-type Linux --runtime python --runtime-version 3.7 \
    --storage-account stgvmautostop

az appservice plan create --name asp-vmautostop --resource-group rg-vmautostop --is-linux --number-of-workers 4 --sku S1

az functionapp create --name fn-vmautostop --resource-group rg-vmautostop \
    --plan asp-vmautostop \
    --os-type Linux --runtime python --runtime-version 3.7 \
    --storage-account stgvmautostop

az functionapp config appsettings list --name fn-vmautostop \
    --resource-group rg-vmautostop 

az functionapp config appsettings set --name fn-vmautostop \
    --resource-group rg-vmautostop \
	--settings FUNCTIONS_EXTENSION_VERSION=~3

az functionapp delete --name fn-vmautostop --resource-group rg-vmautostop

func init fn-vmautostop --worker-runtime python
cd fn-vmautostop
func azure functionapp fetch-app-settings fn-vmautostop
func new --name vmautostop  --template "TimerTrigger"
func azure functionapp publish fn-vmautostop --build remote
func start
func azure functionapp publish fn-vmautostop --build remote --publish-local-settings

az group delete --name rg-vmautostop1 --yes --no-wait
az group create --name rg-vmautostop1 --location WestUS
az group deployment create --resource-group rg-vmautostop1 \
    --template-file vmautostop-func-cons.json --parameters @vmautostop-func-cons.parameters.json 

az group deployment create --resource-group rg-vmautostop1 \
    --template-file vmautostop-func-dynamic.json \
    --parameters '{ "sendGridApiKey": {"value": "yourSgkey"}, 
                    "warningEmailFrom": {"value": "vmautostop@youremail.com"}, 
                    "warningEmailTo" :{"value": "John.Doe@youremail.com"}}'

az group deployment create --resource-group rg-vmautostop3 \
    --template-file vmautostop-func-dedicated.json \
    --parameters '{ "sendGridApiKey": {"value": "yourSgkey"}, 
                    "warningEmailFrom": {"value": "vmautostop@youremail.com"}, 
                    "warningEmailTo" :{"value": "John.Doe@youremail.com"}}'

az storage account keys list --account-name stgvasaie6jbczrs3bk
func azure functionapp publish fn-vmautostop-aie6jbczrs3bk --build remote --publish-local-settings
func azure functionapp publish fn-vmautostop-qdyj3x6uay7nc --build remote 

az role definition create --role-definition ./vmautostop-role.json
az role definition delete --name "Virtual Machine Auto Stop" --subscription 00000000-0000-0000-0000-000000000000 
az functionapp show --name "<fuction app name>" --resource-group "<resource group name>" --query 'identity.principalId'

az role assignment create --assignee "<service principle id>" \
     --role "Virtual Machine Auto Stop" \
     --subscription "<subscription id>"

az role assignment list --subscription "<subscription id>"
