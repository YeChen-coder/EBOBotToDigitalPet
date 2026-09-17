import { adapterName } from './aws-config.mjs';

// Business deployment selection is explicit. Never infer it from container reachability:
// a stopped deployment must not silently fail over and compete for the same login/input.
export function runtimeEnvironment(config) {
  if (!['local', 'aws', 'stopped'].includes(config.runtimeEnvironment)) throw new Error('runtimeEnvironment must be local, aws or stopped');
  return config.runtimeEnvironment;
}
export function activeTargets(config) {
  const environment = runtimeEnvironment(config);
  if (environment === 'stopped') return [];
  return config.targets.filter(t => t.enabled !== false &&
    (environment === 'aws' ? adapterName(t) === 'aws-ecs' : adapterName(t) === 'docker'));
}
