@description('Project internal workspace resource ID')
param projectWorkspaceId string

var workspaceSegments = split(projectWorkspaceId, '/workspaces/')
var projectWorkspaceIdGuid = length(workspaceSegments) > 1 ? workspaceSegments[1] : projectWorkspaceId

output projectWorkspaceIdGuid string = projectWorkspaceIdGuid
