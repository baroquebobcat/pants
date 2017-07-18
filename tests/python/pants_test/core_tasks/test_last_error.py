# coding=utf-8
# Copyright 2017 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import (absolute_import, division, generators, nested_scopes, print_function,
                        unicode_literals, with_statement)

import os

from unittest import expectedFailure

from pants.core_tasks.last_error import LastError
from pants.goal.goal import Goal
from pants.goal.task_registrar import TaskRegistrar
from pants.task.task import Task
from pants_test.pants_run_integration_test import PantsRunIntegrationTest


class LastErrorTest(PantsRunIntegrationTest):

  def test_no_log_file(self):
    with self.temporary_workdir() as workdir:
      pants_result = self.run_pants_with_workdir(['last-error'], workdir)
      self.assertIn('No previous error in logs.', pants_result.stdout_data)

  def test_file_with_no_contents(self):
    with self.temporary_workdir() as workdir:
      os.mkdir(os.path.join(workdir, 'logs'))
      with open(os.path.join(workdir, 'logs/exceptions.log'), 'w') as f:
        f.write('')

      pants_result = self.run_pants_with_workdir(['last-error'], workdir)
      self.assertIn('No previous error in logs.', pants_result.stdout_data)

  def test_existing_error(self):
    with self.temporary_workdir() as workdir:
      pants_result = self.run_pants_with_workdir(['list', 'non-existent-dir::'], workdir)
      self.assert_failure(pants_result)

      pants_result = self.run_pants_with_workdir(['last-error'], workdir)
      self.assertIn('Error from ', pants_result.stdout_data)
      self.assertIn('list non-existent-dir::', pants_result.stdout_data)
      self.assertIn('Path "non-existent-dir" contains no BUILD files.', pants_result.stdout_data)
