targetScope = 'subscription'

@minLength(1)
@maxLength(64)
@description('Name which is used to generate a short unique hash for each resource')
param environment string
@description('Object ID of the user that will be used to deploy the resources. See readme for more details.')
param principalId string
@minLength(1)
@description('Primary location for all resources')
param location string
// https://learn.microsoft.com/azure/ai-services/openai/concepts/models?tabs=global-standard%2Cstandard-chat-completions#models-by-deployment-type
@description('Location for the OpenAI resources')
@allowed([
  'australiaeast'
  'brazilsouth'
  'canadaeast'
  'eastus'
  'eastus2'
  'francecentral'
  'germanywestcentral'
  'japaneast'
  'koreacentral'
  'northcentralus'
  'norwayeast'
  'polandcentral'
  'southafricanorth'
  'southcentralus'
  'southindia'
  'spaincentral'
  'swedencentral'
  'switzerlandnorth'
  'uaenorth'
  'uksouth'
  'westeurope'
  'westus'
  'westus3'
])
@metadata({
  azd: {
    type: 'location'
  }
})
param openAiLocation string
@description('Primary location for cohere serverless deployment')
@allowed(['eastus', 'eastus2', 'westus','westus3','northcentralus','southcentralus','swedencentral'])
@metadata({
  azd: {
    type: 'location'
  }
})
param cohereServerlessLocation string

var resourcePrefix = loadJsonContent('abbreviations.json')
var resourceToken = toLower(uniqueString(subscription().id, environment, location))
var deploymentNamePrefix = take(resourceToken, 6)
var tags = { 'azd-env-name': environment }
var rgName = environment

var searchIndexName = 'state-of-ai'
var knowledgeAgentName = 'state-of-ai-knowledge-agent'
var mmArtifacts = 'mm-knowledgestore-artifacts'
var mmSampleDocs = 'mm-sample-docs-container'
var openAiModelName = 'gpt-4o'
var openAiDeploymentName = 'gpt-4o'
var multiModalEmbeddingModel = 'Cohere-embed-v3-multilingual'
var openAiEmbeddingModelName = 'text-embedding-3-large'
var cogServicesName = '${resourcePrefix.cognitiveServicesAccounts}${resourceToken}'
var searchServiceName = '${resourcePrefix.searchSearchServices}${resourceToken}'
var webAppName = 'mm${resourcePrefix.webSitesAppService}${resourceToken}'
var storageAccountName = '${resourcePrefix.storageStorageAccounts}${resourceToken}'

resource resourceGroup 'Microsoft.Resources/resourceGroups@2021-04-01' = {
  name: rgName
  location: location
  tags: tags
}

module searchService 'searchService/searchService.bicep' = {
  name: 'searchService-${deploymentNamePrefix}-deployment'
  scope: resourceGroup
  params: {
    location: location
    name: searchServiceName
  }
}

module aiFoundry 'ai/main.bicep' = {
  name: 'aiFoundry-${deploymentNamePrefix}-deployment'
  scope: resourceGroup
  params: {
    aiServicesName: cogServicesName
    openAILocation: openAiLocation
    oaimodelName: openAiModelName
    oaiDeploymentName: openAiDeploymentName
    cohereModelName: multiModalEmbeddingModel
    oaiEmbeddingModelName: openAiEmbeddingModelName
    location: location
    cohereLocation: cohereServerlessLocation
    tags: tags
  }
}

module storageAccount 'storage/storage-account.bicep' = {
  name: 'storageAccount-${deploymentNamePrefix}-deployment'
  scope: resourceGroup
  params: {
    storageAccountName: storageAccountName
    location: location
    tags: tags
    allowedAppOrigin: 'https://${webAppName}.azurewebsites.net'
    skuName: 'Standard_LRS'
  }
}

var appsettings = {
  DOCUMENTINTELLIGENCE_ENDPOINT: aiFoundry.outputs.aiServicesEndpoint
  SEARCH_SERVICE_ENDPOINT: searchService.outputs.endpoint
  SEARCH_INDEX_NAME: searchIndexName
  AZURE_INFERENCE_EMBED_ENDPOINT: aiFoundry.outputs.embbeddingEndpoint
  AZURE_INFERENCE_EMBED_MODEL_NAME: aiFoundry.outputs.cohereModelName
  AZURE_OPENAI_ENDPOINT: aiFoundry.outputs.openAiTarget
  AZURE_OPENAI_MODEL_NAME: aiFoundry.outputs.openAIModelName
  AZURE_OPENAI_DEPLOYMENT: aiFoundry.outputs.oaiDeploymentName
  ARTIFACTS_STORAGE_ACCOUNT_URL: storageAccount.outputs.accountPrimaryEndpoints.blob
  ARTIFACTS_STORAGE_CONTAINER: mmArtifacts
  SAMPLES_STORAGE_CONTAINER: mmSampleDocs
  KNOWLEDGE_AGENT_NAME: knowledgeAgentName
}

module appservice 'host/appservices.bicep' = {
  name: 'appService-${deploymentNamePrefix}-deployment'
  scope: resourceGroup
  params: {
    webAppName: webAppName
    location: location
    linuxFxVersion: 'python|3.13'
    sku: 'B1'
    appsettings: appsettings
  }
}

// USER ROLES
// Storage Blob Data Contributor
module storageRoleUser 'security/role.bicep' = {
  scope: resourceGroup
  name: 'storage-role-user'
  params: {
    principalId: principalId
    roleDefinitionId: 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
    principalType: 'User'
  }
}

// Cognitive Services User
module cogUser 'security/role.bicep' = {
  scope: resourceGroup
  name: 'cog-user'
  params: {
    principalId: principalId
    roleDefinitionId: 'a97b65f3-24c7-4388-baec-2e87135dc908'
    principalType: 'User'
  }
}

// Search service index data contributor
module searchIndexRole 'security/role.bicep' = {
  scope: resourceGroup
  name: 'search-index-contributor'
  params: {
    principalId: principalId
    roleDefinitionId: '8ebe5a00-799e-43f5-93ac-243d3dce84a7'
    principalType: 'User'
  }
}

// Search service contributor
module searchServiceRole 'security/role.bicep' = {
  scope: resourceGroup
  name: 'search-service-contributor'
  params: {
    principalId: principalId
    roleDefinitionId: '7ca78c08-252a-4471-8644-bb5ff32d4ba0'
    principalType: 'User'
  }
}

// Azure AI developer
module aiDevRole 'security/role.bicep' = {
  scope: resourceGroup
  name: 'ai-dev-role'
  params: {
    principalId: principalId
    roleDefinitionId: '64702f94-c441-49e6-a78b-ef80e0188fee'
    principalType: 'User'
  }
}

// APP ROLES
// Storage Blob Data Contributor
module storageRoleApp 'security/role.bicep' = {
  scope: resourceGroup
  name: 'storage-role-app'
  params: {
    principalId: appservice.outputs.webAppPrincipalId
    roleDefinitionId: 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
    principalType: 'ServicePrincipal'
  }
}

// Cognitive Services openai User
module cogOpenAIApp 'security/role.bicep' = {
  scope: resourceGroup
  name: 'cog-openai-app'
  params: {
    principalId: appservice.outputs.webAppPrincipalId
    roleDefinitionId: '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'
    principalType: 'ServicePrincipal'
  }
}

// Cognitive Services openai User
module cogApp 'security/role.bicep' = {
  scope: resourceGroup
  name: 'cog-app'
  params: {
    principalId: appservice.outputs.webAppPrincipalId
    roleDefinitionId: 'a97b65f3-24c7-4388-baec-2e87135dc908'
    principalType: 'ServicePrincipal'
  }
}

// Search service index data contributor
module searchIndexRoleApp 'security/role.bicep' = {
  scope: resourceGroup
  name: 'search-index-contributor-App'
  params: {
    principalId: appservice.outputs.webAppPrincipalId
    roleDefinitionId: '8ebe5a00-799e-43f5-93ac-243d3dce84a7'
    principalType: 'ServicePrincipal'
  }
}

// Search service contributor
module searchServiceRoleApp 'security/role.bicep' = {
  scope: resourceGroup
  name: 'search-service-contributor-App'
  params: {
    principalId: appservice.outputs.webAppPrincipalId
    roleDefinitionId: '7ca78c08-252a-4471-8644-bb5ff32d4ba0'
    principalType: 'ServicePrincipal'
  }
}

// Azure AI developer
module aiDevRoleApp 'security/role.bicep' = {
  scope: resourceGroup
  name: 'ai-dev-roleApp'
  params: {
    principalId: appservice.outputs.webAppPrincipalId
    roleDefinitionId: '64702f94-c441-49e6-a78b-ef80e0188fee'
    principalType: 'ServicePrincipal'
  }
}


// RBAC for search service
// Storage Blob Data Contributor
module storageRoleUser2 'security/role.bicep' = {
  scope: resourceGroup
  name: 'storage-role-user2'
  params: {
    principalId: searchService.outputs.principalId
    roleDefinitionId: 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
    principalType: 'ServicePrincipal'
  }
}

// Cognitive Services openai User
module cogOpenAIUser2 'security/role.bicep' = {
  scope: resourceGroup
  name: 'cog-openai-user2'
  params: {
    principalId: searchService.outputs.principalId
    roleDefinitionId: '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'
    principalType: 'ServicePrincipal'
  }
}

// Cognitive Services User
module cogUser2 'security/role.bicep' = {
  scope: resourceGroup
  name: 'cog-user2'
  params: {
    principalId: searchService.outputs.principalId
    roleDefinitionId: 'a97b65f3-24c7-4388-baec-2e87135dc908'
    principalType: 'ServicePrincipal'
  }
}

output DOCUMENTINTELLIGENCE_ENDPOINT string = aiFoundry.outputs.aiServicesEndpoint
output SEARCH_SERVICE_ENDPOINT string = searchService.outputs.endpoint
output SEARCH_INDEX_NAME string = searchIndexName
output AZURE_INFERENCE_EMBED_ENDPOINT string = aiFoundry.outputs.embbeddingEndpoint
output AZURE_INFERENCE_EMBED_API_KEY string = aiFoundry.outputs.embeddingKey
output AZURE_INFERENCE_EMBED_MODEL_NAME string = aiFoundry.outputs.cohereModelName
output AZURE_OPENAI_ENDPOINT string = aiFoundry.outputs.openAiTarget
output AZURE_OPENAI_DEPLOYMENT string = aiFoundry.outputs.oaiDeploymentName
output AZURE_OPENAI_MODEL_NAME string = aiFoundry.outputs.openAIModelName
output ARTIFACTS_STORAGE_ACCOUNT_URL string = storageAccount.outputs.accountPrimaryEndpoints.blob
output ARTIFACTS_STORAGE_CONTAINER string = mmArtifacts
output SAMPLES_STORAGE_CONTAINER string = mmSampleDocs
output AZURE_WEBAPP_URL string = appservice.outputs.webAppUri
output AZURE_WEBAPP_PRINCIPAL_ID string = appservice.outputs.webAppPrincipalId
output AZURE_OPENAI_EMBEDDING_DEPLOYMENT string = openAiEmbeddingModelName
output KNOWLEDGE_AGENT_NAME string = knowledgeAgentName
output AZURE_RESOURCE_GROUP string = rgName
