# coding=utf-8
# Copyright 2015 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import (absolute_import, division, generators, nested_scopes, print_function,
                        unicode_literals, with_statement)

import os

from pants.backend.jvm.targets.jvm_target import JvmTarget
from pants.backend.jvm.tasks.classpath_util import ClasspathUtil
from pants.base.exceptions import TaskError
from pants.goal.products import UnionProducts
from pants_test.base_test import BaseTest


class ClasspathUtilTest(BaseTest):
  def test_path_with_differing_conf_ignored(self):
    a = self.make_target('a', JvmTarget)

    classpath_product = UnionProducts()

    path = os.path.join(self.build_root, 'jar/path')
    classpath_product.add_for_target(a, [('default', path)])

    classpath = ClasspathUtil.compute_classpath([a], classpath_product, [], ['not-default'])

    self.assertEqual([], classpath)

  def test_path_with_overlapped_conf_added(self):
    a = self.make_target('a', JvmTarget)

    classpath_product = UnionProducts()

    path = os.path.join(self.build_root, 'jar/path')
    classpath_product.add_for_target(a, [('default', path)])

    classpath = ClasspathUtil.compute_classpath([a], classpath_product, [],
                                                ['not-default', 'default'])

    self.assertEqual([path], classpath)


  def test_extra_path_added(self):
    a = self.make_target('a', JvmTarget)

    classpath_product = UnionProducts()

    path = os.path.join(self.build_root, 'jar/path')
    classpath_product.add_for_target(a, [('default', path)])

    extra_path = 'new-path'
    classpath = ClasspathUtil.compute_classpath([a], classpath_product,
                                                [('default', extra_path)], ['default'])

    self.assertEqual([path, extra_path], classpath)

  def test_complains_about_paths_outside_buildroot(self):
    a = self.make_target('a', JvmTarget)

    classpath_product = UnionProducts()
    classpath_product.add_for_target(a, [('default', '/dev/null')])

    with self.assertRaises(TaskError) as cm:
      ClasspathUtil.compute_classpath([a], classpath_product, [], ['default'])

    self.assertEqual(
      str('Classpath entry /dev/null for target a:a is located outside the buildroot.'),
      str(cm.exception))
