# Read-only GitLab 19.5.3 compiler/Rules check, run with gitlab-rails runner -.
# Replace SOURCE_FILES_BASE64 with base64 JSON of ONLY the three source CI files.
# This never calls CreatePipelineService, save!, a job API, or Vault.
# Local fetch replacement is confined to this disposable Ruby process: it lets
# the real include compiler read unpublished source without changing Git refs.
require 'base64'
require 'json'
require 'ostruct'
require 'digest'

begin
  gate = 'source_input'
  input = JSON.parse(Base64.strict_decode64('SOURCE_FILES_BASE64'))
  root = JSON.parse(input.fetch('.gitlab-ci.yml'))
  proof = JSON.parse(input.fetch('.gitlab/vault-layout-proof.yml'))
  normal = input.fetch('.gitlab/ci.yml')
  baseline = 'a25c6010b0b3202421a95b536700653cb83d4c3a'
  expected_hash = 'ac0be3887e4611efb9ceb9e10faec109248579e193708bfd719e108e3f1090f6'
  raise unless Digest::SHA256.hexdigest(normal) == expected_hash
  raise unless Gitlab::VERSION == '19.5.3'
  project = Project.find(1)
  user = User.find_by!(username: 'dev-machine')
  raise unless project.full_path == 'downops/wallet-tracker-backend'
  raise unless project.ci_config_path == '.gitlab-ci.yml'
  raise unless project.repository.blob_at(baseline, '.gitlab/ci.yml').data == normal

  # Only source files are substituted, only in this process, not on disk/Gitaly.
  submitted_files = input
  local_files = Module.new do
    define_method(:fetch_local_content) { submitted_files.fetch(location) }
  end
  Gitlab::Ci::Config::External::File::Local.prepend(local_files)
  checked = 0
  [nil, '', 'true', 'false', 'TRUE'].product(%w[api web push schedule merge_request_event]).each do |flag, source|
    gate = "variable_phase_#{checked}"
    attrs = flag.nil? ? [] : [{ key: 'VAULT_LAYOUT_PROOF_ONLY', value: flag }]
    pipeline = ::Ci::Pipeline.new(project: project, user: user, ref: 'dev', sha: baseline, source: source)
    # API association assignment ultimately supplies pipeline.variables. Build
    # unsaved test associations directly, bypassing the artifact/persistence and
    # pipeline-service steps entirely. Phase wiring is separately source-checked.
    attrs.each { |attr| pipeline.variables.build(attr) }
    raise if pipeline.persisted? || pipeline.variables.any?(&:persisted?)
    # Actual pipeline.variables -> config_variables -> include path.
    vars = pipeline.variables_builder.config_variables.to_hash
    raise unless vars['VAULT_LAYOUT_PROOF_ONLY'] == flag
    cfg = Gitlab::Ci::Config.new(input.fetch('.gitlab-ci.yml'), project: project, user: user,
                                pipeline: pipeline, sha: baseline, source: source, inject_edge_stages: false)
    if flag.nil? || flag.empty?
      gate = "normal_merge_#{checked}"
      old = Gitlab::Ci::Config.new(normal, project: project, user: user, pipeline: pipeline,
                                  sha: baseline, source: source, inject_edge_stages: false)
      raise unless cfg.valid? && old.valid? && cfg.to_hash == old.to_hash
    elsif flag == 'true' && %w[api web].include?(source)
      gate = "proof_merge_#{checked}"
      raise unless cfg.valid? && cfg.to_hash.deep_stringify_keys == proof
      rules = Gitlab::Ci::Build::Rules.new(proof.fetch('vault-layout-auth-proof').fetch('rules').map(&:deep_symbolize_keys),
                                         default_when: 'on_success')
      result = rules.evaluate(pipeline, OpenStruct.new(variables_hash: vars))
      gate = "proof_manual_rules_#{checked}"
      raise unless result.pass? && result.when == 'manual' && result.allow_failure == false && !result.errors
    else
      gate = "invalid_mode_#{checked}"
      raise unless (cfg.to_hash.keys.map(&:to_s) - ['include']).empty? && !cfg.valid?
    end
    checked += 1
  end

  # Full boundary predicate matrix through GitLab's own expression engine;
  # synthetic context only, never overrides a live project's variables/config.
  matrix = 0
  gate = 'predicate_matrix'
  [nil, '', 'true', 'false', 'TRUE', ' true', 'true ', '1'].product(
    %w[1 31], ['downops', 'fork/downops'], ['dev', 'main', 'feature/x', nil],
    ['true', 'false', nil], ['api', 'web', 'push', 'merge_request_event', 'schedule', 'trigger',
                            'pipeline', 'parent_pipeline', 'external', nil]).each do |flag, project_id, ns, branch, protected, source|
    vars = { 'VAULT_LAYOUT_PROOF_ONLY' => flag, 'CI_PROJECT_ID' => project_id,
             'CI_PROJECT_NAMESPACE' => ns, 'CI_COMMIT_BRANCH' => branch,
             'CI_COMMIT_REF_PROTECTED' => protected, 'CI_PIPELINE_SOURCE' => source }
    selected = root.fetch('include').select do |entry|
      Gitlab::Ci::Pipeline::Expression::Statement.new(entry.fetch('rules').first.fetch('if'), vars).truthful?
    end.map { |entry| entry.fetch('local') }
    approved = flag == 'true' && project_id == '1' && ns == 'downops' && branch == 'dev' &&
               protected == 'true' && %w[api web].include?(source)
    expected = (flag.nil? || flag.empty?) ? ['.gitlab/ci.yml'] : (approved ? ['.gitlab/vault-layout-proof.yml'] : [])
    raise unless selected == expected
    matrix += 1
  end
  puts JSON.generate(valid: true, version: Gitlab::VERSION, ci_config_path: project.ci_config_path,
                     config_contexts: checked, predicate_contexts: matrix,
                     normal_merged_equal: true, proof_job: 'vault-layout-auth-proof',
                     when: 'manual', allow_failure: false, pipelines_saved: 0, jobs_created: 0,
                     limitation: 'Unpublished local include supplied in disposable compiler process; no auth/rollout proof')
rescue StandardError => e
  # No raw errors/config/variables/API data: errors could contain private values.
  attribute = e.respond_to?(:attribute) && e.attribute.to_s.match?(/\A[a-z_]+\z/) ? e.attribute : nil
  puts JSON.generate(valid: false, error_class: e.class.name, invalid_attribute: attribute, gate: gate, raw_error_withheld: true)
  exit 1
end
