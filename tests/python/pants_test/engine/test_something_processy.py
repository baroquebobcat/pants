# coding=utf-8
# Copyright 2016 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import (absolute_import, division, generators, nested_scopes, print_function,
                        unicode_literals, with_statement)

import os
import unittest
from abc import abstractmethod
from contextlib import contextmanager

from pants.engine.fs import (Dir, DirectoryListing, Dirs, FileContent, Files, Link, Path, PathGlobs,
                             ReadLink, Stat, Stats)
from pants.engine.nodes import FilesystemNode
from pants.util.meta import AbstractClass
from pants_test.engine.scheduler_test_base import SchedulerTestBase


class SomethingTest(SchedulerTestBase, AbstractClass):

  _original_src = os.path.join(os.path.dirname(__file__), 'examples/fs_test')

  @abstractmethod
  @contextmanager
  def mk_project_tree(self, build_root_src):
    """Construct a ProjectTree for the given src path."""
    pass

  def specs(self, ftype, relative_to, *filespecs):
    return PathGlobs.create_from_specs(ftype, relative_to, filespecs)

  def assert_walk(self, ftype, filespecs, files):
    with self.mk_project_tree(self._original_src) as project_tree:
      scheduler, storage = self.mk_scheduler(project_tree=project_tree)
      result = self.execute(scheduler, storage, Stat, self.specs(ftype, '', *filespecs))[0]
      self.assertEquals(set(files), set([p.path for p in result]))

  def assert_content(self, filespecs, expected_content):
    with self.mk_project_tree(self._original_src) as project_tree:
      scheduler, storage = self.mk_scheduler(project_tree=project_tree)
      result = self.execute(scheduler, storage, FileContent, self.specs(Files, '', *filespecs))[0]
      def validate(e):
        self.assertEquals(type(e), FileContent)
        return True
      actual_content = {f.path: f.content for f in result if validate(f)}
      self.assertEquals(expected_content, actual_content)

  def assert_fsnodes(self, ftype, filespecs, subject_product_pairs):
    with self.mk_project_tree(self._original_src) as project_tree:
      scheduler, storage = self.mk_scheduler(project_tree=project_tree)
      request = self.execute_request(scheduler, storage, Stat, self.specs(ftype, '', *filespecs))

      # Validate that FilesystemNodes for exactly the given subjects are reachable under this
      # request.
      fs_nodes = [n for n, _ in scheduler.product_graph.walk(roots=request.roots)
                  if type(n) is FilesystemNode]
      self.assertEquals(set((n.subject, n.product) for n in fs_nodes), set(subject_product_pairs))

  def test_something(self):
    # build snapshot from existing files.
    # TODO: what to do about incremental?
    ## unpack snapshot into dir w/ name based on files fingerprint + op fingerprint
    #  - if dir exists, op may or may not have already happened or may have partially happened.
    #    - could have a valid vs not notion held somewhere else, so when a something finishes we can
    #      know that it finished and reported success.
    #    - if bit isn't set, then rm the dir
    #  - if no dir, create it and unpack
    #
    ## run op on snapshot
    # - need to have a setup binary
    # - or binary could be part of the snapshot
    # - setting cwd to the unpacked dir
    # - do snapshots depend on other snapshots ala the classpath folders?
    # - what to do with logs? do they go in the snapshot, or a meta snapshot?
    #
    ## fingerprint and  pack unpacked snapshot dir
    # - output vs input?
    #
    ## set validation bit
    ## write packed snapshot somewhere, ie cache

    pass
