# coding=utf-8
# Copyright 2015 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import (absolute_import, division, generators, nested_scopes, print_function,
                        unicode_literals, with_statement)

from pants.engine.nodes import Node, Noop, Return, State, TaskNode, Throw, Waiting
from pants.engine.selectors import Select
from pants.util.objects import datatype


class Snapshot(datatype('Snapshot', ['archive'])):
  pass


#
# Data oriented vs
# Goal oriented
#
# I think we should have data oriented declarations, but goal oriented execution
# So, instead of saying
#   Foo, (Select(Bar), run_baz
# We say
#  Select(Bar), run_baz, Foo
#
#  Or instead of
# (ImportedJVMPackages,
#       [SelectProjection(FilesContent, PathGlobs, ('path_globs',), ScalaInferredDepsSources)],
#       extract_scala_imports)
#
# Select(ScalaInferredDepsSources) pluck('path_globs') construct(PathGlobs) makeSubject Select(FilesContent) extract_scala_imports ImportedJVMPackages
#
# If we have files of S then we can produce concatted of S via concat
#
# If we have checked out a snapshot of S then we can run a process in that snapshot
#
# If we have files of S and root path of S then we can produce a snapshot of S
# If we have a snapshot of S then we can check out a snapshot of S
#
#  snapshot process poc
# concat maybe?
# as in
# root Concatted of Dir('a/b/c')
# (Concatted, (Select(Files)<of S>, Select(RootDir)<of S>),
#             ShellCat<of Global? of itself?>,
#             files_to_prepared_tmp_dir
#
# (Concatted, (Select(RelpathedFiles)<of S>, Select(Snapshot)<of S>)
#
#
# SnapshotInputs(S) :- Files(S), RootPath(S)
#
#
# project product-type of subject() into snapshot of selected (product of subject)
# CheckedOutSnapshot(x) :- Snapshots(x) <untarred>
# Snapshots(x) :-
#
#def files_to_prepared_tmp_dir(files):
#  for f in files:
#    f.path
# (Snapshot, Select(Files), taremup)
class UncacheableTaskNode(TaskNode):
  is_cacheable = False


# input selectors -> project them as snapshots
#
#snapshot from sources
#(Snapshot, [Select(Sources)], create_snapshot)
#
#def create_snapshot(root_dir, sources):
#  source_set = set(sources)
#  def filter(tarinfo):
#    if tarinfo.name == '':
#      return None
#
#    return tarinfo
#  TarArchiver().create(filter=filter)
#
#
class SnapshottedProcessRequest(datatype('SnapshottedProcessRequest',['args', 'temp_dir'])):
  pass


class SnapshottedProcessResult(datatype('SnapshottedProcessResult', ['temp_dir', 'stdout', 'stderr'])):
  pass


class SnapshotNode(datatype('SnapshotNode', ['binary', 'process_request']), Node):
  is_cacheable = False
  is_inlineable = False

  def step(self, step_context):
    raise NotImplementedError('Not used')
    #return Return(
    #  SnapshottedProcessResult('blah', 'stdout', 'stderr')
    #)


class ProcessExecutionNode(datatype('ProcessNode', ['binary', 'process_request']), Node):
  is_cacheable = False
  is_inlineable = False

  def step(self, step_context):
    return Return(
      SnapshottedProcessResult('blah', 'stdout', 'stderr')
    )


class ProcessOrchestrationNode(datatype('ProcessOrchestrationNode', ['subject', 'snapshotted_process']), Node):
  is_cacheable = True
  is_inlineable = False

  def _snapshot_node(self):
    return SnapshotNode()

  def step(self, step_context):
    #create task node with selects for input types and input_to_process_request

    task_state = step_context.get(self._request_task_node())
    if type(task_state) in (Waiting, Throw):
      return task_state
    elif type(task_state) is Noop:
      print('nooooooping 1')
      return Noop('couldnt find something {} while looking for {}'.format(task_state, self.snapshotted_process.input_selectors))
      #return task_state # Maybe need a specific one where
    elif type(task_state) is not Return:
      State.raise_unrecognized(task_state)
    #elif type(task_state) is Return:
    process_request = task_state.value

    print("=============select inputs and map to process request finished!")

    binary_state = step_context.get(self._binary_select_node(step_context))
    if type(binary_state) in (Waiting, Throw):
      return binary_state
    elif type(binary_state) is Noop:
      print('nooooooping 2')
      return Noop('couldnt find something {} while looking for {}'.format(binary_state, self.snapshotted_process.binary_type))
      #return binary_state # Maybe need a specific one where
    elif type(binary_state) is not Return:
      State.raise_unrecognized(binary_state)

    #elif type(binary_state) is Return:
    binary_value = binary_state.value

    print("========binary type found!")

    exec_node = self._process_exec_node(binary_value, process_request)
    exec_state = step_context.get(exec_node)
    if type(exec_state) in (Waiting, Throw):
      return exec_state
    elif type(exec_state) is Noop:
      return Noop('couldnt find something {} while looking for {}'.format(exec_state, binary_value))
      #return exec_state # Maybe need a specific one where
    elif type(exec_state) is not Return:
      State.raise_unrecognized(exec_state)
    #elif type(exec_state) is Return:
    process_result = exec_state.value

    return Return(self.snapshotted_process.output_conversion(process_result))
    #dep_node = step_context.select_node(selector, self.subject, self.variants)
    #dep_state = step_context.get(dep_node)

  def _process_exec_node(self, binary_value, process_request):
    return ProcessExecutionNode(binary_value, process_request)

  def _binary_select_node(self, step_context):
    return step_context.select_node(Select(self.snapshotted_process.binary_type),
                                    # Not sure what the hell these would be yet
                                    subject=None,
                                    variants=None)

  def _request_task_node(self):
    return UncacheableTaskNode(subject=self.subject,
                    product=SnapshottedProcessRequest,
                    variants=None,  # not sure yet
                    func=self.snapshotted_process.input_conversion,
                    clause=self.snapshotted_process.input_selectors)

  #def __repr__(self):
  #  return 'TaskNode(subject={}, product={}, variants={}, func={}, clause={}'\
  #    .format(self.subject, self.product, self.variants, self.func.__name__, self.clause)
  def __str__(self):
    return repr(self)


#Process Rule
#
# I want
# Product of S
# Which is computed by
# finding the products provided by these selectors
# converting a portion of them into a checked out snapshot
# converting them into a process request
# then providing that into a ProcessNode
# and waiting for that to finish

#process_rules= [
#
#  (Snapshot, # of S
#  #  requires
#  [Select(Files)  # of S
#   ],
#
#]
