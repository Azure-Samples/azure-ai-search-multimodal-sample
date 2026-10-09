@description('Base name of the resource such as web app name and app service plan ')
@minLength(2)
param webAppName string
@description('The SKU of App Service Plan ')
param sku string = 'S1'
@description('The Runtime stack of current web app')
param linuxFxVersion string
@description('Location for all resources.')
param location string = resourceGroup().location
param appsettings object = {}
@description('Client ID of a single-tenant Microsoft Entra application registered for this site.')
@minLength(36)
param authClientId string
@secure()
@description('Client secret of the Microsoft Entra application.')
@minLength(1)
param authClientSecret string
@description('Microsoft Entra tenant that issues sign-in tokens.')
@minLength(36)
param authTenantId string

var appServicePlanName = 'AppServicePlan-${webAppName}'

resource appServicePlan 'Microsoft.Web/serverfarms@2022-03-01' = {
  name: appServicePlanName
  location: location
  sku: {
    name: sku
  }
  kind: 'linux'
  properties: {
    reserved: true
  }
}

resource webAppPortal 'Microsoft.Web/sites@2022-03-01' = {
  name: webAppName
  location: location
  tags: { 'azd-service-name': 'backend' }
  kind: 'app'
  properties: {
    serverFarmId: appServicePlan.id
    siteConfig: {
      linuxFxVersion: linuxFxVersion
      ftpsState: 'FtpsOnly'
    }
    httpsOnly: true
  }
  identity: {
    type: 'SystemAssigned'
  }
}

resource siteConfig 'Microsoft.Web/sites/config@2024-04-01' = {
  parent: webAppPortal
  name: 'web'
  properties: {
    netFrameworkVersion: 'v4.0'
    linuxFxVersion: 'PYTHON|3.13'
    requestTracingEnabled: false
    remoteDebuggingEnabled: false
    remoteDebuggingVersion: 'VS2022'
    httpLoggingEnabled: false
    webSocketsEnabled: false
    appCommandLine: 'python -m pip install -r requirements.txt && python app.py'
  }
}

// Add environment variables to app settings
resource appSettings 'Microsoft.Web/sites/config@2022-03-01' = {
  parent: webAppPortal
  name: 'appsettings'
  properties: union(appsettings, {
    MICROSOFT_PROVIDER_AUTHENTICATION_SECRET: authClientSecret
  })
}

resource authentication 'Microsoft.Web/sites/config@2022-09-01' = {
  parent: webAppPortal
  name: 'authsettingsV2'
  properties: {
    platform: {
      enabled: true
    }
    globalValidation: {
      requireAuthentication: true
      unauthenticatedClientAction: 'RedirectToLoginPage'
      redirectToProvider: 'azureactivedirectory'
    }
    httpSettings: {
      requireHttps: true
      forwardProxy: {
        convention: 'NoProxy'
      }
    }
    identityProviders: {
      azureActiveDirectory: {
        enabled: true
        registration: {
          clientId: authClientId
          clientSecretSettingName: 'MICROSOFT_PROVIDER_AUTHENTICATION_SECRET'
          openIdIssuer: '${environment().authentication.loginEndpoint}${authTenantId}/v2.0'
        }
        validation: {
          allowedAudiences: [
            authClientId
          ]
        }
      }
    }
    login: {
      tokenStore: {
        enabled: false
      }
    }
  }
  dependsOn: [
    appSettings
  ]
}


output webAppPrincipalId string = webAppPortal.identity.principalId
output webAppUri string = 'https://${webAppPortal.properties.defaultHostName}'
