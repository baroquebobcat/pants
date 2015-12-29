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
from pants.backend.jvm.jar_dependency_utils import ResolvedJar
from pants.backend.jvm.targets.jar_library import JarLibrary
from pants.backend.jvm.targets.jvm_binary import JvmBinary
from pants.backend.jvm.tasks.classpath_products import ClasspathProducts
from pants.backend.jvm.tasks.ivy_task_mixin import IvyTaskMixin, IvyResolveFingerprintStrategy
from pants.backend.jvm.tasks.nailgun_task import NailgunTask
from pants.binaries import binary_util
from pants.invalidation.cache_manager import VersionedTargetSet
from pants.util.dirutil import safe_mkdir
from pants.util.memo import memoized_property
from pants.util.strutil import safe_shlex_split


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
    jar_to_versions = defaultdict(lambda: defaultdict(lambda: 0))
    target_to_binaries = defaultdict(set)
    binary_to_3rdparty_lib_to_resolved_versions = defaultdict(lambda: defaultdict(set))
    sets_of_jar_libraries=set()
    thirdparty_lib_to_resolved_versions = defaultdict(set)
    executor = self.create_java_executor()
    print('binaries: {}'.format(len(binaries)))
    bi = 0
    fingerprinter = IvyResolveFingerprintStrategy(self.get_options().confs)
    for b in binaries:
      bi +=1
      fingerprint = self._cache_key_generator.key_for_target(b, transitive=True, fingerprint_strategy=fingerprinter)

      print('Binary: {} ({}/{})'.format(b.address.spec, bi, len(binaries)))
      print('  fingerprint: {}'.format(fingerprint))
      b_closure = b.closure()
      for t in b_closure:
        target_to_binaries[t].add(b)

      b_cp = ClasspathProducts(self.get_options().pants_workdir)
      thirdparty_lib_to_resolved_versions = binary_to_3rdparty_lib_to_resolved_versions[b]
      resolve_hash_name = self.resolve(executor=executor,
                                     targets=b_closure,
                                     classpath_products=b_cp,
                                     confs=self.get_options().confs,
                                     extra_args=self._args,
                                     jar_to_versions=jar_to_versions,
                                     sets_of_jar_libraries=sets_of_jar_libraries,
                                     thirdparty_lib_to_resolved_versions=thirdparty_lib_to_resolved_versions)
    

    print()
    for j, vct in sorted(jar_to_versions.items(), key=lambda x: len(x[1])):
      print('{} ct:{}'.format(j, len(vct)))
      for v, ct in sorted(vct.items(), key=lambda x: x[1]):
        print('  {}: {}'.format(v,ct))
    ct_targets_w_more_than_one_set = 0
    
    for t in targets:
      bs = target_to_binaries.get(t)
      t_3rdparty_libs = [tt for tt in t.closure() if isinstance(t, JarLibrary)]
      if not bs:
        if t not in binaries:
          print('no binaries for {}'.format(t.address.spec))
        continue
      ext_dep_sets = set()
      for b in bs:
        set_for_b = set()
        erdparty_lib_to_resolved_versions = binary_to_3rdparty_lib_to_resolved_versions[b]
        for tt in t_3rdparty_libs:
          set_for_b.update(erdparty_lib_to_resolved_versions[tt])
        ext_dep_sets.add(tuple(set_for_b))
      if len(ext_dep_sets) > 1:
        print('for {}'.format(t.address.spec))
        print('  sets of ext_deps: {}'.format(len(ext_dep_sets)))
        ct_targets_w_more_than_one_set += 1
    print()
    print('sets_of_jar_libraries:               {}'.format(len(sets_of_jar_libraries)) )
    print('total bin/test targets:              {}'.format(len(binaries)))
    print('non-bin/test targets w/ > 1 dep set: {}'.format(ct_targets_w_more_than_one_set))
    print('all targets           :              {}'.format(len(targets)))
    #targets = self.context.targets()
    #compile_classpath = self.context.products.get_data('compile_classpath',
    #    init_func=ClasspathProducts.init_func(self.get_options().pants_workdir))
    #resolve_hash_name = self.resolve(executor=executor,
    #                                 targets=targets,
    #                                 classpath_products=compile_classpath,
    #                                 confs=self.get_options().confs,
    #                                 extra_args=self._args)
    #if self._report:
    #  self._generate_ivy_report(resolve_hash_name)


  # CP + and modify from ivy_task_mixin
  def resolve(self, executor, targets, classpath_products, confs=None, extra_args=None,
              invalidate_dependents=False,jar_to_versions=None,sets_of_jar_libraries=None,thirdparty_lib_to_resolved_versions=None):
    """Resolves external classpath products (typically jars) for the given targets.

    :param executor: A java executor to run ivy with.
    :type executor: :class:`pants.java.executor.Executor`
    :param targets: The targets to resolve jvm dependencies for.
    :type targets: :class:`collections.Iterable` of :class:`pants.build_graph.target.Target`
    :param classpath_products: The classpath products to populate with the results of the resolve.
    :type classpath_products: :class:`pants.backend.jvm.tasks.classpath_products.ClasspathProducts`
    :param confs: The ivy configurations to resolve; ('default',) by default.
    :type confs: :class:`collections.Iterable` of string
    :param extra_args: Any extra command line arguments to pass to ivy.
    :type extra_args: list of string
    :param bool invalidate_dependents: `True` to invalidate dependents of targets that needed to be
                                        resolved.
    :returns: The id of the reports associated with this resolve.
    :rtype: string
    """

    classpath_products.add_excludes_for_targets(targets)

    confs = confs or ('default',)

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
        raise self.UnresolvedJarError('Jar {resolved_jar} in {spec} not resolved to the ivy '
                                      'symlink map in conf {conf}.'
                                      .format(spec=tgt.address.spec,
                                              resolved_jar=resolved_jar_without_symlink.cache_path,
                                              conf=cnf))
    print('CONFS: {!r}'.format(confs))
    # Build the 3rdparty classpath product.
    for conf in confs:
      print('  C:{}'.format(conf))
      ivy_info = self._parse_report(resolve_hash_name, conf)
      if not ivy_info:
        continue
      ivy_jar_memo = {}
      jar_library_targets = [t for t in targets if isinstance(t, JarLibrary)]
      sets_of_jar_libraries.add(tuple(sorted(set(jar_library_targets))))
      print('    jar_librarys')
      for target in jar_library_targets:
        print('      {}'.format(target.address.spec))
        # Add the artifacts from each dependency module.
        raw_resolved_jars = ivy_info.get_resolved_jars_for_jar_library(target, memo=ivy_jar_memo)
        resolved_jars = [new_resolved_jar_with_symlink_path(target, conf, raw_resolved_jar)
                         for raw_resolved_jar in raw_resolved_jars]
        thirdparty_lib_to_resolved_versions[target] = resolved_jars
        for r in resolved_jars:
          print('        {!s}'.format(r.coordinate))
          jar_to_versions[r.coordinate.id_without_rev][r.coordinate.rev]+=1
        classpath_products.add_jars_for_targets([target], conf, resolved_jars)

    return resolve_hash_name

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
