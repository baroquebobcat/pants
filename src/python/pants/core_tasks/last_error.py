# coding=utf-8
# Copyright 2017 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import (absolute_import, division, generators, nested_scopes, print_function,
                        unicode_literals, with_statement)


import os

from pants.task.console_task import ConsoleTask


class LastError(ConsoleTask):
  """Print the last error's traceback."""

  def console_output(self, targets):

      error_text = self.last_error_text()
      if not error_text:
        yield 'No previous error in logs.'
      else:
        yield error_text

  def last_error_text(self):
    exception_log_path = os.path.join(self.context.options.for_global_scope().pants_workdir, 'logs',
      'exceptions.log')

    try:
      with open(exception_log_path) as f:
        contents = f.read()
    except IOError:
      return None

    begin = contents.rfind('\ntimestamp: ')
    if not begin:
      return None
    return contents[begin:-1]
