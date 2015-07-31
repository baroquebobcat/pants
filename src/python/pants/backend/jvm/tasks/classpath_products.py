# coding=utf-8
# Copyright 2015 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import (absolute_import, division, generators, nested_scopes, print_function,
                        unicode_literals, with_statement)

import os

from pants.backend.jvm.targets.jvm_target import JvmTarget
from pants.base.build_environment import get_buildroot
from pants.base.exceptions import TaskError
from pants.goal.products import UnionProducts


def _not_excluded_filter(exclude_patterns):
  def not_excluded(path_tuple):
    conf, path = path_tuple
    return not any(excluded in path for excluded in exclude_patterns)
  return not_excluded


class ClasspathProducts(object):
  def __init__(self):
    self._classpaths = UnionProducts()
    self._exclude_patterns = UnionProducts()

  def add_for_targets(self, targets, classpath_elements):
    """Adds classpath elements to the products of all the provided targets."""
    for target in targets:
      self.add_for_target(target, classpath_elements)

  def add_for_target(self, target, classpath_elements):
    """Adds classpath elements to the products of the provided target."""
    self._classpaths.add_for_target(target, classpath_elements)

  def add_excludes_for_targets(self, targets):
    """Add excludes from the provided targets. Does not look up transitive excludes."""
    for target in targets:
      self._add_excludes_for_target(target)

  def get_for_target(self, target):
    """Gets the transitive classpath products for the given target, in order, respecting target
       excludes."""
    classpath_tuples = self._classpaths.get_for_target(target)

    filtered_classpath_tuples = self._filter_by_excludes(classpath_tuples, [target])

    return filtered_classpath_tuples

  def get_for_targets(self, targets):
    """Gets the transitive classpath products for the given targets, in order, respecting target
       excludes."""
    classpath_tuples = self._classpaths.get_for_targets(targets)
    filtered_classpath_tuples = self._filter_by_excludes(classpath_tuples, targets)
    return filtered_classpath_tuples

  def _filter_by_excludes(self, classpath_tuples, root_targets):
    exclude_patterns = self._exclude_patterns.get_for_targets(root_targets)
    filtered_classpath_tuples = filter(_not_excluded_filter(exclude_patterns),
                                       classpath_tuples)
    return filtered_classpath_tuples

  def _add_excludes_for_target(self, target):
    # creates strings from excludes that will match classpath entries generated by ivy
    # eg exclude(org='org.example', name='lib') => 'jars/org.example/lib'
    #    exclude(org='org.example')             => 'jars/org.example/'
    if target.is_exported:
      self._exclude_patterns.add_for_target(target,
                                            [os.path.join('jars',
                                                          target.provides.org,
                                                          target.provides.name)])
    if isinstance(target, JvmTarget) and target.excludes:
      self._exclude_patterns.add_for_target(target,
                                            [os.path.join('jars', e.org, e.name or '')
                                             for e in target.excludes])
