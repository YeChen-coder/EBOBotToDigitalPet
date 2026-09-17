// One-time operator setup. The running Bridge never imports IAM APIs or administrator credentials.
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { readConfig } from '../src/common.mjs';
import { awsPolicies } from '../src/aws-policy.mjs';
import { createAwsCli, awsError } from '../src/aws-cli.mjs';

const execute = process.argv.includes('--execute');
const target = readConfig().targets.find(t => t.id === 'cloud-ebo' && t.adapter === 'aws-ecs');
if (!target) throw new Error('Missing cloud-ebo configuration');
const hostPath = path.resolve('local/aws-host.json');
const host = JSON.parse(fs.readFileSync(hostPath, 'utf8'));
const connection = host.connections[target.aws.connection];
const reader = await createAwsCli(connection, target)(['sts', 'get-caller-identity']);
const userName = 'ebo-diagnostics-reader', roleName = 'EboRuntimeControl';
const readerArn = `arn:aws:iam::${target.aws.accountId}:user/ebo-diagnostics/${userName}`;
if (reader.Account !== target.aws.accountId || reader.Arn !== readerArn) throw new Error('Expected dedicated diagnostics reader identity');
const roleArn = `arn:aws:iam::${target.aws.accountId}:role/ebo-diagnostics/${roleName}`;
const dir = path.resolve('local/iam'); fs.mkdirSync(dir, { recursive: true });
const policies = {
  'runtime-trust': { Version:'2012-10-17',Statement:[{Effect:'Allow',Principal:{AWS:readerArn},Action:'sts:AssumeRole'}] },
  'runtime-control': awsPolicies(target).control,
  'runtime-assume': { Version:'2012-10-17',Statement:[{Effect:'Allow',Action:'sts:AssumeRole',Resource:roleArn}] },
};
for (const [name,policy] of Object.entries(policies)) fs.writeFileSync(path.join(dir, name+'.json'),JSON.stringify(policy,null,2));
if (!execute) {
  console.log(JSON.stringify({prepared:true,roleArn,readerArn,service:target.aws.service,policies:Object.keys(policies),note:'No IAM permissions changed. Run with --execute to install.'}));
} else {
  const admin = JSON.parse(fs.readFileSync('local/aws-provision-admin.json','utf8'));
  const env = {...process.env};for(const key of Object.keys(env))if(key.startsWith('AWS_'))delete env[key];
  Object.assign(env,{AWS_CONFIG_FILE:admin.configFile,AWS_SHARED_CREDENTIALS_FILE:admin.credentialsFile,AWS_LOGIN_CACHE_DIRECTORY:admin.loginCacheDirectory,
    AWS_PAGER:'',AWS_CLI_AUTO_PROMPT:'off',AWS_CLI_FILE_ENCODING:'UTF-8',AWS_CLI_OUTPUT_ENCODING:'UTF-8'});
  function aws(args,missingOkay=false){
    try{return JSON.parse(execFileSync(admin.cliPath,[...args,'--profile',admin.readProfile,'--region',target.aws.region,'--output','json','--no-cli-pager','--no-cli-auto-prompt'],
      {env,encoding:'utf8',windowsHide:true,timeout:30000,stdio:['ignore','pipe','pipe']})||'{}');}
    catch(e){if(missingOkay&&/NoSuchEntity/.test(String(e.stderr)))return null;throw new Error(`Runtime setup failed at ${args.slice(0,2).join(' ')}: ${awsError(e)}; credential values omitted`);}
  }
  if(aws(['sts','get-caller-identity']).Account!==target.aws.accountId)throw new Error('Administrator account mismatch');
  const file=name=>'file://'+path.join(dir,name+'.json').replaceAll('\\','/');
  let role=aws(['iam','get-role','--role-name',roleName],true)?.Role;
  if(role && (role.Path!=='/ebo-diagnostics/' || !role.Tags?.some(t=>t.Key==='ManagedBy'&&t.Value==='EBO-Diagnostics')))throw new Error('Existing role is not owned by this project');
  if(!role)role=aws(['iam','create-role','--role-name',roleName,'--path','/ebo-diagnostics/','--assume-role-policy-document',file('runtime-trust'),'--tags','Key=ManagedBy,Value=EBO-Diagnostics']).Role;
  else aws(['iam','update-assume-role-policy','--role-name',roleName,'--policy-document',file('runtime-trust')]);
  aws(['iam','put-role-policy','--role-name',roleName,'--policy-name','EboRuntimeServiceControl','--policy-document',file('runtime-control')]);
  aws(['iam','put-user-policy','--user-name',userName,'--policy-name','AssumeEboRuntimeControl','--policy-document',file('runtime-assume')]);
  // Separate config, same source credentials. No new access key is created or printed.
  const sourceFile=connection.runtimeSourceConfigFile||connection.configFile;
  const controlFile=path.resolve('local/host/aws-runtime-config');
  const source=fs.readFileSync(sourceFile,'utf8');
  fs.writeFileSync(controlFile,source+`\n[profile ebo-runtime-control]\nrole_arn=${roleArn}\nsource_profile=${connection.readProfile}\nregion=${target.aws.region}\noutput=json\n`,{mode:0o600});
  Object.assign(connection,{configFile:controlFile,runtimeSourceConfigFile:sourceFile,controlProfile:'ebo-runtime-control',allowRuntimeControl:true});
  fs.writeFileSync(hostPath+'.tmp',JSON.stringify(host,null,2),{mode:0o600});fs.renameSync(hostPath+'.tmp',hostPath);
  console.log(JSON.stringify({installed:true,roleArn,service:target.aws.service,controlProfile:connection.controlProfile,newAccessKeys:0,note:'Restart the host Bridge. No business services were started or stopped.'}));
}
