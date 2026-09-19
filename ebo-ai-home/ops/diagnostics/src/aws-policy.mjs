import { validateAwsTarget } from './aws-config.mjs';

// Generate reviewable policies; this module never creates identities or grants permissions.
export function awsPolicies(target) {
  validateAwsTarget(target);
  const a = target.aws; const ecs = `arn:aws:ecs:${a.region}:${a.accountId}`;
  const cluster = `${ecs}:cluster/${a.cluster}`;
  const region = { StringEquals: { 'aws:RequestedRegion': a.region } };
  const read = { Version: '2012-10-17', Statement: [
    { Sid: 'ConfiguredService', Effect: 'Allow', Action: ['ecs:DescribeServices'], Resource: `${ecs}:service/${a.cluster}/${a.service}` },
    { Sid: 'ClusterTaskStates', Effect: 'Allow', Action: ['ecs:DescribeTasks'], Resource: `${ecs}:task/${a.cluster}/*` },
    { Sid: 'ListClusterTasks', Effect: 'Allow', Action: ['ecs:ListTasks'], Resource: '*', Condition: { ArnEquals: { 'ecs:cluster': cluster } } },
    { Sid: 'ConfiguredLogs', Effect: 'Allow', Action: ['logs:FilterLogEvents'],
      Resource: [...new Set(a.containers.map(c => `arn:aws:logs:${a.region}:${a.accountId}:log-group:${c.logGroup}:*`))] },
    // AWS does not offer resource-level permissions for GetMetricStatistics.
    { Sid: 'RegionalMetricStatistics', Effect: 'Allow', Action: ['cloudwatch:GetMetricStatistics'], Resource: '*', Condition: region },
    // Cost Explorer does not support resource-level permissions. The dashboard caches this paid API for six hours.
    { Sid: 'AccountCostSummary', Effect: 'Allow', Action: ['ce:GetCostAndUsage'], Resource: '*' },
  ] };
  const action = { Version: '2012-10-17', Statement: [
    ...read.Statement.filter(s => ['ConfiguredService', 'ClusterTaskStates', 'ListClusterTasks'].includes(s.Sid)),
    { Sid: 'StopObservedClusterTask', Effect: 'Allow', Action: ['ecs:StopTask'], Resource: `${ecs}:task/${a.cluster}/*`, Condition: { ArnEquals: { 'ecs:cluster': cluster } } },
  ] };
  const control = { Version: '2012-10-17', Statement: [
    ...read.Statement.filter(s => ['ConfiguredService', 'ClusterTaskStates', 'ListClusterTasks'].includes(s.Sid)),
    { Sid: 'SetConfiguredServiceCount', Effect: 'Allow', Action: ['ecs:UpdateService'], Resource: `${ecs}:service/${a.cluster}/${a.service}` },
    { Sid: 'CheckRegionalScaling', Effect: 'Allow', Action: ['application-autoscaling:DescribeScalableTargets'], Resource: '*', Condition: region },
  ] };
  return { read, action, control };
}
