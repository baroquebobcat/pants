# coding=utf-8
# Copyright 2015 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import (absolute_import, division, generators, nested_scopes, print_function,
                        unicode_literals, with_statement)

import os
import shutil
import time
from textwrap import dedent
from collections import defaultdict

from pants.backend.jvm.ivy_utils import IvyUtils
from pants.backend.jvm.targets.jar_dependency import JarDependency
from pants.backend.jvm.jar_dependency_utils import ResolvedJar, M2Coordinate
from pants.backend.jvm.targets.jar_library import JarLibrary
from pants.backend.jvm.targets.jvm_binary import JvmBinary
from pants.backend.jvm.tasks.classpath_products import ClasspathProducts
from pants.backend.jvm.tasks.ivy_task_mixin import IvyTaskMixin, IvyResolveFingerprintStrategy
from pants.backend.jvm.tasks.nailgun_task import NailgunTask
from pants.binaries import binary_util
from pants.invalidation.cache_manager import VersionedTargetSet
from pants.util.dirutil import safe_mkdir, safe_open
from pants.util.memo import memoized_property
from pants.util.strutil import safe_shlex_split


RESOLVED_JAR_CACHE = dict()

def get_or_create_resolved_jar(org, name, rev, classifier, ext):
  t = (org, name, rev, classifier, ext)
  r = RESOLVED_JAR_CACHE.get(t)
  if not r:
    r = ResolvedJar(M2Coordinate(org, name, rev, classifier, ext), 'TODO', 'TODO')
    RESOLVED_JAR_CACHE[t]=r
  return r


class LoadFromFreezeResult(object):
  """Collects the results from loading a FREEZE file."""
  def __init__(self, valid):
    self._valid = valid
    self.target_to_resolved_jars = defaultdict(set)

  def successful(self):
    return self._valid

  def add_resolved_artifact_for_target(self,current_thirdparty_target, resolved_jar):
    self.target_to_resolved_jars[current_thirdparty_target].add(resolved_jar)

  @property
  def resolved_jars(self):
    for jar_set in self.target_to_resolved_jars.values():
      for jar in jar_set:
        yield jar

class BlahResolve(IvyTaskMixin, NailgunTask):

  @classmethod
  def register_options(cls, register):
    super(BlahResolve, cls).register_options(register)
    register('--override', action='append',
             fingerprint=True,
             help='Specifies a jar dependency override in the form: '
             '[org]#[name]=(revision|url) '
             'Multiple overrides can be specified using repeated invocations of this flag. '
             'For example, to specify 2 overrides: '
             '--override=com.foo#bar=0.1.2 '
             '--override=com.baz#spam=file:///tmp/spam.jar ')
    register('--report', action='store_true', default=False,
             help='Generate an ivy resolve html report')
    register('--open', action='store_true', default=False,
             help='Attempt to open the generated ivy resolve report '
                  'in a browser (implies --report)')
    register('--outdir', help='Emit ivy report outputs in to this directory.')
    register('--args', action='append',
             fingerprint=True,
             help='Pass these extra args to ivy.')
    register('--confs', action='append', default=['default'],
             help='Pass a configuration to ivy in addition to the default ones.')
    register('--mutable-pattern',
             fingerprint=True,
             help='If specified, all artifact revisions matching this pattern will be treated as '
                  'mutable unless a matching artifact explicitly marks mutable as False.')
    cls.register_jvm_tool(register,
                          'xalan',
                          classpath=[
                            JarDependency(org='xalan', name='xalan', rev='2.7.1'),
                          ])

  @classmethod
  def product_types(cls):
    return ['compile_classpath']

  @classmethod
  def prepare(cls, options, round_manager):
    super(BlahResolve, cls).prepare(options, round_manager)
    round_manager.require_data('java')
    round_manager.require_data('scala')

  def __init__(self, *args, **kwargs):
    super(BlahResolve, self).__init__(*args, **kwargs)

    self._outdir = self.get_options().outdir or os.path.join(self.workdir, 'reports')
    self._open = self.get_options().open
    self._report = self._open or self.get_options().report

    self._args = []
    for arg in self.get_options().args:
      self._args.extend(safe_shlex_split(arg))

  def read_freeze_file(self, frozen_file, fingerprint):
    if not os.path.exists(frozen_file):
      return LoadFromFreezeResult(valid=False)

    with safe_open(frozen_file, 'rb') as ff:
      # Read fingerprint
      fingerprint_line = ff.readline()
      _, fingerprint_from_file = fingerprint_line.split(':')
      fingerprint_from_file = fingerprint_from_file.strip()
      if fingerprint_from_file != fingerprint:
        return LoadFromFreezeResult(valid=False)

      result = LoadFromFreezeResult(valid=True)
      # parse rest of file
      ff.readline() # JAR_LIBRARIES line
      current_thirdparty_target = None
      for line in ff:
        if line.startswith('    '): # i.e. it's a jar line
          if current_thirdparty_target is None:
            raise Exception('No way. can\'t deal with no current thirdparty.')

          # ensure that they are None rather than empty string
          org, name, rev, classifier, ext = [x or None for x in line.strip().split(':')]
          resolved_jar = get_or_create_resolved_jar(org, name, rev, classifier, ext)

          result.add_resolved_artifact_for_target(current_thirdparty_target, resolved_jar)
        elif line.startswith('  '): # i.e. it's a jar lib line
          spec = line.strip()
          current_thirdparty_target = self.context.build_graph.get_target_from_spec(spec)
      self.context.log.debug('  loaded from file')
      return result

  def write_to_freeze_file(self, frozen_file, fingerprint, target_to_resolved_jars):
    with safe_open(frozen_file, 'wb') as f:
      f.write('FINGERPRINT: {}\n'.format(fingerprint))
      f.write('JAR_LIBRARIES:\n')
      for thirdparty_lib, jars in target_to_resolved_jars.items():
        f.write('  {}\n'.format(thirdparty_lib.address.spec))
        for r in jars:
          # TODO hash of jars too*
          f.write('    {!s}\n'.format(r.coordinate))


  def gen_fingerprint(self, b, fingerprinter):
    cache_key = self._cache_key_generator.key_for_target(b, transitive=True, fingerprint_strategy=fingerprinter)
    if cache_key is None:
      return None

    return cache_key.hash

  def execute(self):
    """Resolves the specified confs for the configured targets and returns an iterator over
    tuples of (conf, jar path).
    """
    target_roots = self.context.target_roots

    targets = self.context.targets()
    binaries = sorted([t for t in targets if isinstance(t, JvmBinary) or t.is_test], key=lambda k: k.address.spec)
    # get all the binaries
    # for each
    #   fingerprint em
    #   get their closure
    #   get their excludes
    #   get the set of their 3rdparty libs
    #   print out the 3rdparty libs
    #
    #   resolve their closure and get the ivy info
    #

    # rm frozen things
    #    find . -name 'FREEZE.*' -exec rm {} \;
    jar_to_versions = defaultdict(lambda: defaultdict(lambda: 0))
    target_to_binaries = defaultdict(set)
    binary_to_3rdparty_lib_to_resolved_versions = defaultdict(lambda: defaultdict(set))
    sets_of_jar_libraries=set()
    thirdparty_lib_to_resolved_versions = defaultdict(set)

    executor = self.create_java_executor()
    fingerprinter = IvyResolveFingerprintStrategy(self.get_options().confs)

    print('binaries: {}'.format(len(binaries)))
    bi = 0

    def inc_versions(result):
      for resolved_jar in result.resolved_jars:
        jar_to_versions[resolved_jar.coordinate.id_without_rev][resolved_jar.coordinate.rev]+=1

    loaded_from_file_results = []
    loaded_from_file_targets = []
    try:
      for b in binaries:
        bi += 1
        self.context.log.debug('Binary: {} ({}/{})'.format(b.address.spec, bi, len(binaries)))

        fingerprint = self.gen_fingerprint(b, fingerprinter)
        if fingerprint is None:
          self.context.log.debug('  No fingerprint for it. Skipping')
          continue


        b_closure = b.closure()
        for t in b_closure:
          target_to_binaries[t].add(b)

        frozen_file = '{}/FREEZE.{}'.format(b.address.spec_path, b.address.target_name)

        self.context.log.debug('  fingerprint: {}'.format(fingerprint))

        jar_library_targets = [t for t in b_closure if isinstance(t, JarLibrary)]
        sets_of_jar_libraries.add(frozenset(jar_library_targets))

        result = self.read_freeze_file(frozen_file, fingerprint)

        if result.successful():
          binary_to_3rdparty_lib_to_resolved_versions[b] = result.target_to_resolved_jars
          loaded_from_file_results.append(result)
          loaded_from_file_targets.append(b)

          inc_versions(result)
        else:
          self.context.log.debug(' resolving')

          thirdparty_lib_to_resolved_versions = binary_to_3rdparty_lib_to_resolved_versions[b]
          b_cp = ClasspathProducts(self.get_options().pants_workdir)
          resolve_result = self.resolve(executor=executor,
                                         targets=b_closure,
                                         classpath_products=b_cp,
                                         extra_args=self._args,
                                         jar_library_targets=jar_library_targets)

          inc_versions(result)

          self.write_to_freeze_file(frozen_file, fingerprint, thirdparty_lib_to_resolved_versions)

    except BaseException as e:
      print('!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!')
      print('!!with exception!!: {}'.format(e))
      print('!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!')

    # collect all the load from FREEZE file artifacts and bulk fetch them
    #loaded_from_file_results
    # TODO cache here
    resolve_hash_name='some-hash'
    with IvyUtils.ivy_lock:
      # construct jar dependencies from the resolved jars from the from file list
      jjjars = set()
      original_resolved_coords = set()
      for result in loaded_from_file_results:
        for j in result.resolved_jars:
          jc = j.coordinate
          original_resolved_coords.add(jc)
          jjj = JarDependency(jc.org, jc.name,
                              rev=jc.rev,
                              #force=False,
                              ext=jc.ext,
                              #url=None,
                              #apidocs=None,
                              classifier=jc.classifier,
                              #mutable=None,
                              intransitive=True,
                              #excludes=None
                              )
          jjjars.add(jjj)
        #jjjars.update(result.resolved_jars)
      ivyxml = os.path.join(self.context._buildroot, 'poc-ivy.xml')
      IvyUtils.generate_ivy(loaded_from_file_targets,
                            jjjars, 
                            excludes=[], 
                            ivyxml=ivyxml,
                            confs=('default',),
                            resolve_hash_name=resolve_hash_name,
                            ignore_conflicts=True
                            )
      # resolve
      self._really_exec_ivy(ivy=None,
                            confs_to_resolve=('default',),
                            ivyxml=ivyxml,
                            executor=executor,
                            workunit_name='resolve-frozen',
                            args=[])
    jar_targets = set()
    for result in loaded_from_file_results:
      jar_targets.update(result.target_to_resolved_jars.keys())
    full_load_results = self.load2_result_from_report(jar_targets, resolve_hash_name, 'default')
    full_coords = {j.coordinate for j in full_load_results.resolved_jars}
    print('resolve coords == requested? {}'.format(full_coords == original_resolved_coords))
    print('resolve - requested\n    {}'.format(full_coords - original_resolved_coords))
    print('requested - resolved\n    {}'.format('\n    '.join(sorted(str(x) for x in original_resolved_coords - full_coords))))

    return
    with self.context.new_workunit('stats'):
      # summary
      print()
      for j, vct in sorted(jar_to_versions.items(), key=lambda x: len(x[1])):
        print('{} ct:{}'.format(j, len(vct)))
        for v, ct in sorted(vct.items(), key=lambda x: x[1]):
          print('  {}: {}'.format(v,ct))
      ct_targets_w_more_than_one_set = defaultdict(lambda: 0)

      print()
      print()
  #date "+%Y-%m-%dT%H-%M-%S"
      for t in targets:
        # skip 3rdparty targets for the purpose of checking # of sets
        if isinstance(t, JarLibrary):
          continue

        bs = target_to_binaries.get(t)

        # if none, then the target has no dependent binaries / tests
        if not bs:
          #if t not in binaries:
          #  #print('no binaries for {}'.format(t.address.spec))
          continue

        t_3rdparty_libs = [tt for tt in t.closure() if isinstance(tt, JarLibrary)]
        ext_dep_sets = set()
        for b in bs:
          list_for_b = []
          erdparty_lib_to_resolved_versions = binary_to_3rdparty_lib_to_resolved_versions[b]
          for tt in t_3rdparty_libs:
            list_for_b.extend(erdparty_lib_to_resolved_versions[tt])
          set_for_b = frozenset(list_for_b)
          for ext_set in ext_dep_sets:
            if set_for_b <= ext_set:
              break
          else:
            ext_dep_sets.add(set_for_b)

          if len(ext_dep_sets) > 10:
            break
        if len(ext_dep_sets) > 1:
          #print('for {}'.format(t.address.spec))
          #print('  sets of ext_deps: {}'.format(len(ext_dep_sets)))
          #for s in ext_dep_sets:
          #  print('    - {}'.format(s))
          #break
          key = len(ext_dep_sets) if (len(ext_dep_sets) < 11) else '> 10'
          ct_targets_w_more_than_one_set[key] += 1


      print()
      print('sets_of_jar_libraries:               {}'.format(len(sets_of_jar_libraries)) )
      print('total bin/test targets:              {}'.format(len(binaries)))
      print('non-bin/test targets w/ > 1 dep set: {}'.format(sum(ct_targets_w_more_than_one_set.values())))
      for no, ct in ct_targets_w_more_than_one_set.items():
        print('    {}: {}'.format(no, ct))
      print('all targets           :              {}'.format(len(targets)))

  # CP + and modify from ivy_task_mixin
  def resolve(self, executor, targets, classpath_products, conf=None, extra_args=None,
              invalidate_dependents=False, jar_library_targets=None):
    """Resolves external classpath products (typically jars) for the given targets.

    :param executor: A java executor to run ivy with.
    :type executor: :class:`pants.java.executor.Executor`
    :param targets: The targets to resolve jvm dependencies for.
    :type targets: :class:`collections.Iterable` of :class:`pants.build_graph.target.Target`
    :param classpath_products: The classpath products to populate with the results of the resolve.
    :type classpath_products: :class:`pants.backend.jvm.tasks.classpath_products.ClasspathProducts`
    :param conf: The ivy configuration to resolve; 'default' by default.
    :type conf: :class:`collections.Iterable` of string
    :param extra_args: Any extra command line arguments to pass to ivy.
    :type extra_args: list of string
    :param bool invalidate_dependents: `True` to invalidate dependents of targets that needed to be
                                        resolved.
    :returns: The id of the reports associated with this resolve.
    :rtype: string
    """

    classpath_products.add_excludes_for_targets(targets)
    if conf:
      confs = (conf,)
    else:
      confs = ('default',)

    # After running ivy, we parse the resulting report, and record the dependencies for
    # all relevant targets (ie: those that have direct dependencies).
    _, symlink_map, resolve_hash_name = self.ivy_resolve(
      targets,
      executor=executor,
      workunit_name='ivy-resolve',
      confs=confs,
      custom_args=extra_args,
      invalidate_dependents=invalidate_dependents,
    )

    if not resolve_hash_name:
      # There was no resolve to do, so no 3rdparty deps to process below
      return

    # Record the ordered subset of jars that each jar_library/leaf depends on using
    # stable symlinks within the working copy.

    # Build the 3rdparty classpath product.
    return self.load_result_from_report(jar_library_targets, resolve_hash_name, conf, symlink_map)
      #classpath_products.add_jars_for_targets([target], conf, resolved_jars)
    #return result

  def load_result_from_report(self, jar_library_targets, resolve_hash_name, conf, symlink_map={}):
    def new_resolved_jar_with_symlink_path(tgt, cnf, resolved_jar_without_symlink):
      # There is a focus on being lazy here to avoid `os.path.realpath` when we can.
      def candidate_cache_paths():
        yield resolved_jar_without_symlink.cache_path
        yield os.path.realpath(resolved_jar_without_symlink.cache_path)

      try:
        return next(ResolvedJar(coordinate=resolved_jar_without_symlink.coordinate,
                                pants_path=symlink_map[cache_path],
                                cache_path=resolved_jar_without_symlink.cache_path)
                    for cache_path in candidate_cache_paths() if cache_path in symlink_map)
      except StopIteration:

        return resolved_jar_without_symlink
        #raise self.UnresolvedJarError('Jar {resolved_jar} in {spec} not resolved to the ivy '
        #                              'symlink map in conf {conf}.'
        #                              .format(spec=tgt.address.spec,
        #                                      resolved_jar=resolved_jar_without_symlink.cache_path,
        #                                      conf=cnf))

    ivy_info = self._parse_report(resolve_hash_name, conf)
    if not ivy_info:
      return LoadFromFreezeResult(valid=False)
    ivy_jar_memo = {}
    result = LoadFromFreezeResult(valid=True)
    for target in jar_library_targets:
      # Add the artifacts from each dependency module.
      raw_resolved_jars = ivy_info.get_resolved_jars_for_jar_library(target, memo=ivy_jar_memo)
      for raw_resolved_jar in raw_resolved_jars:
        resolved_jar = new_resolved_jar_with_symlink_path(target, conf, raw_resolved_jar)
        result.add_resolved_artifact_for_target(target, resolved_jar)
    return result


  def load2_result_from_report(self, jar_library_targets, resolve_hash_name, conf, symlink_map={}):
    def new_resolved_jar_with_symlink_path(tgt, cnf, resolved_jar_without_symlink):
      # There is a focus on being lazy here to avoid `os.path.realpath` when we can.
      def candidate_cache_paths():
        yield resolved_jar_without_symlink.cache_path
        yield os.path.realpath(resolved_jar_without_symlink.cache_path)

      try:
        return next(ResolvedJar(coordinate=resolved_jar_without_symlink.coordinate,
                                pants_path=symlink_map[cache_path],
                                cache_path=resolved_jar_without_symlink.cache_path)
                    for cache_path in candidate_cache_paths() if cache_path in symlink_map)
      except StopIteration:

        return resolved_jar_without_symlink
        #raise self.UnresolvedJarError('Jar {resolved_jar} in {spec} not resolved to the ivy '
        #                              'symlink map in conf {conf}.'
        #                              .format(spec=tgt.address.spec,
        #                                      resolved_jar=resolved_jar_without_symlink.cache_path,
        #                                      conf=cnf))

    ivy_info = self._parse_report(resolve_hash_name, conf)
    if not ivy_info:
      return LoadFromFreezeResult(valid=False)

    result = LoadFromFreezeResult(valid=True)


    for jar_ref, artifacts in ivy_info._artifacts_by_ref.items():
      for jar_path in artifacts:
        result.add_resolved_artifact_for_target(None, 
                                                ResolvedJar(coordinate=M2Coordinate(org=jar_ref.org,
                                                                                    name=jar_ref.name,
                                                                                    rev=jar_ref.rev,
                                                                                    classifier=jar_ref.classifier,
                                                                                    ext=jar_ref.ext),
                                                            cache_path=jar_path))

    return result


  def check_artifact_cache_for(self, invalidation_check):
    # Ivy resolution is an output dependent on the entire target set, and is not divisible
    # by target. So we can only cache it keyed by the entire target set.
    global_vts = VersionedTargetSet.from_versioned_targets(invalidation_check.all_vts)
    return [global_vts]

  def _generate_ivy_report(self, resolve_hash_name):
    def make_empty_report(report, organisation, module, conf):
      no_deps_xml_template = dedent("""<?xml version="1.0" encoding="UTF-8"?>
        <?xml-stylesheet type="text/xsl" href="ivy-report.xsl"?>
        <ivy-report version="1.0">
          <info
            organisation="{organisation}"
            module="{module}"
            revision="latest.integration"
            conf="{conf}"
            confs="{conf}"
            date="{timestamp}"/>
        </ivy-report>
        """).format(
        organisation=organisation,
        module=module,
        conf=conf,
        timestamp=time.strftime('%Y%m%d%H%M%S'),
        )
      with open(report, 'w') as report_handle:
        print(no_deps_xml_template, file=report_handle)

    tool_classpath = self.tool_classpath('xalan')

    report = None
    org = IvyUtils.INTERNAL_ORG_NAME
    name = resolve_hash_name
    xsl = os.path.join(self.ivy_cache_dir, 'ivy-report.xsl')

    # Xalan needs this dir to exist - ensure that, but do no more - we have no clue where this
    # points.
    safe_mkdir(self._outdir, clean=False)

    for conf in self.get_options().confs:
      xml_path = self._get_report_path(conf, resolve_hash_name)
      if not os.path.exists(xml_path):
        # Make it clear that this is not the original report from Ivy by changing its name.
        xml_path = xml_path[:-4] + "-empty.xml"
        make_empty_report(xml_path, org, name, conf)
      out = os.path.join(self._outdir,
                         '{org}-{name}-{conf}.html'.format(org=org, name=name, conf=conf))
      args = ['-IN', xml_path, '-XSL', xsl, '-OUT', out]

      # The ivy-report.xsl genrates tab links to files with extension 'xml' by default, we
      # override that to point to the html files we generate.
      args.extend(['-param', 'extension', 'html'])

      if 0 != self.runjava(classpath=tool_classpath, main='org.apache.xalan.xslt.Process',
                           args=args, workunit_name='report'):
        raise self.Error('Failed to create html report from xml ivy report.')

      # The ivy-report.xsl is already smart enough to generate an html page with tab links to all
      # confs for a given report coordinate (org, name).  We need only display 1 of the generated
      # htmls and the user can then navigate to the others via the tab links.
      if report is None:
        report = out

    css = os.path.join(self._outdir, 'ivy-report.css')
    if os.path.exists(css):
      os.unlink(css)
    shutil.copy(os.path.join(self.ivy_cache_dir, 'ivy-report.css'), self._outdir)

    if self._open and report:
      binary_util.ui_open(report)

  def _get_report_path(self, conf, resolve_hash_name):
    try:
      return IvyUtils.xml_report_path(self.ivy_cache_dir, resolve_hash_name, conf)
    except IvyUtils.BlahResolveReportError as e:
      raise self.Error('Failed to generate ivy report: {}'.format(e))
