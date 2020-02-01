mkdir vmautostop
cd vmautostop
mkdir azure
python3.7 venv env
pip install -r requirements.txt
az group create --name rg-vmautostop -location southeastasia
az storage account create --name stgvmautostop --resource-group rg-vmautostop
az functionapp create --name fn-vmautostop --resource-group rg-vmautostop --consumption-plan-location southeastasia 
    --os-type Linux --runtime python --runtime-version 3.7 --storage-account stgvmautostop
az functionapp config appsettings set --name fn-vmautostop \
	--resource-group rg-vm-autostop --settings FUNCTIONS_EXTENSION_VERSION=~3.0

func init fn-vmautostop --worker-runtime python
cd fn-vmautostop
func azure functionapp fetch-app-settings fn-vmautostop
func new --name vmautostop  --template "TimerTrigger"
func azure functionapp publish fn-vmautostop --build remote
func start
func azure functionapp publish fn-vmautostop --build remote --publish-local-settings