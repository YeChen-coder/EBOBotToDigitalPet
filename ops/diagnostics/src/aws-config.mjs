// Public target settings contain resource identifiers, never credentials or host paths.
export function validateAwsTarget(t) {
  const a = t.aws;
  if (t.probe !== 'aws-ecs' || !a || !/^[a-z][a-z0-9-]+$/.test(a.connection || '') ||
      !/^\d{12}$/.test(a.accountId || '') || !/^[a-z]{2}(?:-[a-z]+)+-\d$/.test(a.region || '') ||
      ![a.cluster, a.service].every(x => typeof x === 'string' && /^[\w-]{1,255}$/.test(x))) throw new Error('Invalid AWS target');
  for (const [key, fallback, min, max] of [
    ['pollSeconds', 60, 30, 3600], ['snapshotMaxAgeSeconds', 180, 60, 7200],
    ['healthMaxAgeSeconds', 180, 30, 3600], ['selfHealingSeconds', 300, 60, 1800],
    ['recoverySeconds', 300, 60, 1800], ['logWindowSeconds', 600, 60, 3600],
    ['maxLogPages', 3, 1, 10],
  ]) {
    a[key] ??= fallback;
    if (!Number.isInteger(a[key]) || a[key] < min || a[key] > max) throw new Error(`Invalid AWS ${key}`);
  }
  if (a.snapshotMaxAgeSeconds < a.pollSeconds * 2) throw new Error('AWS snapshot lifetime too short');
  if (!Array.isArray(a.containers) || !a.containers.length || a.containers.length > 10) throw new Error('Missing AWS containers');
  const names = new Set();
  for (const c of a.containers) {
    if (!/^[\w-]{1,255}$/.test(c.name || '') || names.has(c.name) ||
        !/^[\w/.-]{1,512}$/.test(c.logGroup || '') || !/^[\w/.-]{1,512}$/.test(c.streamPrefix || '') ||
        !['ebo-health', 'engine-health', 'container'].includes(c.probe)) throw new Error('Invalid AWS container');
    names.add(c.name);
  }
  return t;
}

export const adapterName = t => t.adapter || 'docker';
