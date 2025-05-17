<#
.SYNOPSIS
    Configures the application with search index and storage parameters using Azure AI Search portal's multimodal wizard.
    This will also update the web app settings if provided.

.DESCRIPTION
    This script sets up application parameters including search index name, search service endpoint,
    storage account URL, and knowledge store container name.

.PARAMETER SearchIndexName
    Name of the Azure AI Search index to use.

.PARAMETER SearchServiceEndpoint
    Endpoint URL for the Azure AI Search service.

.PARAMETER StorageAccountUrl
    URL of the Azure Storage account.

.PARAMETER KnowledgeStoreContainerName
    Name of the container in Azure Storage that holds knowledge store artifacts.

.PARAMETER DataSourcesContainerName
    Name of the container in Azure Storage that holds your data.
.EXAMPLE
    .\portal-2-app.ps1 `
        -SearchIndexName "my-index" `
        -SearchServiceEndpoint "https://myservice.search.windows.net" `
        -StorageAccountUrl "https://myaccount.blob.core.windows.net" `
        -KnowledgeStoreContainerName "mm-knowledgestore-artifacts" `
        -DataSourcesContainerName "mm-data-sources" `
        -AzureOpenAiEndpoint "https://myopenai.openai.azure.com" `
        -AzureOpenAiDeploymentName "my-deployment" `
        -AzureOpenAiEndpointChatCompletionModelName "gpt-4o"
#>

param(
    [Parameter(Mandatory = $true)]
    [string]$SearchIndexName,

    [Parameter(Mandatory = $true)]
    [string]$SearchServiceEndpoint,

    [Parameter(Mandatory = $true)]
    [string]$StorageAccountUrl,

    [Parameter(Mandatory = $true)]
    [string]$KnowledgeStoreContainerName,

    [Parameter(Mandatory = $true)]
    [string]$DataSourcesContainerName,

    [Parameter(Mandatory = $true)]
    [string]$AzureOpenAiEndpoint,

    [Parameter(Mandatory = $true)]
    [string]$AzureOpenAiDeploymentName,

    [Parameter(Mandatory = $true)]
    [string]$AzureOpenAiEndpointChatCompletionModelName,

    [Parameter(Mandatory = $false)]
    [string]$KnowledgeAgentName = "my-knowledge-agent"
   
)

# Check if an azd environment exists, if not, create one
try {
    $azdEnv = azd env get-values --output json | ConvertFrom-Json
} catch {
    Write-Host "No azd environment found. Creating a new environment..."
    $defaultEnvName = "my-multimodal-env"
    azd env new $defaultEnvName
    $azdEnv = azd env get-values --output json | ConvertFrom-Json
}

# Set AZD Environment Variables
azd env set SEARCH_INDEX_NAME $SearchIndexName
azd env set SEARCH_SERVICE_ENDPOINT $SearchServiceEndpoint
azd env set ARTIFACTS_STORAGE_ACCOUNT_URL $StorageAccountUrl
azd env set ARTIFACTS_STORAGE_CONTAINER $KnowledgeStoreContainerName
azd env set SAMPLES_STORAGE_CONTAINER $DataSourcesContainerName
azd env set AZURE_OPENAI_ENDPOINT $AzureOpenAiEndpoint
azd env set AZURE_OPENAI_DEPLOYMENT $AzureOpenAiDeploymentName
azd env set AZURE_OPENAI_MODEL_NAME $AzureOpenAiEndpointChatCompletionModelName
azd env set KNOWLEDGE_AGENT_NAME $KnowledgeAgentName

