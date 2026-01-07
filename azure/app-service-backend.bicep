// Simple App Service Backend - Reliable Alternative to Container Apps
@description('Location for all resources')
param location string = 'eastus2'

@description('Resource group name')
param resourceGroupName string

@description('App Service Plan SKU')
@allowed(['F1', 'B1', 'B2', 'S1'])
param appServicePlanSku string = 'B1'

@description('App Service name')
param appServiceName string = 'gait-analysis-api-appservice'

@description('Container Registry for images')
param containerRegistry string

var appServicePlanName = '${appServiceName}-plan'

// App Service Plan
resource appServicePlan 'Microsoft.Web/serverfarms@2023-01-01' = {
  name: appServicePlanName
  location: location
  kind: 'linux'
  properties: {
    reserved: true // Linux
  }
  sku: {
    name: appServicePlanSku
    tier: appServicePlanSku == 'F1' ? 'Free' : 'Basic'
  }
}

// App Service
resource appService 'Microsoft.Web/sites@2023-01-01' = {
  name: appServiceName
  location: location
  kind: 'app,linux,container'
  properties: {
    serverFarmId: appServicePlan.id
    siteConfig: {
      linuxFxVersion: 'DOCKER|${containerRegistry}.azurecr.io/gait-analysis-api:latest'
      alwaysOn: appServicePlanSku != 'F1' // Always on for paid plans
      http20Enabled: true
      minTlsVersion: '1.2'
      appSettings: [
        {
          name: 'DOCKER_REGISTRY_SERVER_URL'
          value: 'https://${containerRegistry}.azurecr.io'
        }
        {
          name: 'DOCKER_REGISTRY_SERVER_USERNAME'
          value: containerRegistry
        }
        {
          name: 'DOCKER_REGISTRY_SERVER_PASSWORD'
          value: '@Microsoft.KeyVault(SecretUri=https://gait-analysis-kv.vault.azure.net/secrets/acr-password/)'
        }
        {
          name: 'WEBSITES_ENABLE_APP_SERVICE_STORAGE'
          value: 'false'
        }
        {
          name: 'PORT'
          value: '8000'
        }
        {
          name: 'CORS_ORIGINS'
          value: 'https://jolly-meadow-0a467810f.1.azurestaticapps.net,http://localhost:3000,http://localhost:5173'
        }
      ]
    }
    httpsOnly: true
  }
}

// Get connection strings from existing resources
resource storageAccount 'Microsoft.Storage/storageAccounts@2023-01-01' existing = {
  name: 'gaitanalysisprodstorwus3'
}

resource cosmosAccount 'Microsoft.DocumentDB/databaseAccounts@2023-01-01' existing = {
  name: 'gaitanalysisprodcosmoswus3'
}

output appServiceUrl string = 'https://${appService.properties.defaultHostName}'
output appServiceName string = appServiceName



