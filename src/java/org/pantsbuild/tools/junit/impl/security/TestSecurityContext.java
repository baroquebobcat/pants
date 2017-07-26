package org.pantsbuild.tools.junit.impl.security;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/**
 * The context that wraps a test or suite so that the security manager can determine what to do.
 */
public interface TestSecurityContext {
  void addFailure(Exception ex);

  List<Exception> getFailures();

  @Override
  String toString();

  ThreadGroup getThreadGroup();

  String getClassName();

  class TestCaseSecurityContext implements TestSecurityContext {

    private String className;
    private ThreadGroup threadGroup;
    private final String methodName;
    private Exception failureException;

    public TestCaseSecurityContext(String className, String methodName) {
      this.className = className;
      this.threadGroup = new ThreadGroup(className + "-m-" + methodName + "-Threads");
      this.methodName = methodName;
    }

    public ThreadGroup getThreadGroup() {
      return threadGroup;
    }

    @Override
    public String getClassName() {
      return className;
    }

    @Override
    public void addFailure(Exception ex) {
      failureException = ex;
    }

    @Override
    public List<Exception> getFailures() {
      if (failureException == null) {
        return Collections.emptyList();
      }
      List<Exception> list = new ArrayList<>();
      list.add(failureException);
      return list;
    }

    @Override
    public String toString() {
      return "TestCaseSecurityContext{" +
          className + "#" + methodName +
          ", threadGroup=" + threadGroup +
          ", threadGroupActiveCt=" + threadGroup.activeCount() +
          ", failureException=" + failureException +
          '}';
    }
  }

  class SuiteTestSecurityContext implements TestSecurityContext {

    @Override
    public void addFailure(Exception ex) {

    }

    @Override
    public List<Exception> getFailures() {
      return null;
    }

    @Override
    public ThreadGroup getThreadGroup() {
      return null;
    }

    @Override
    public String getClassName() {
      return null;
    }
  }
}
