package org.pantsbuild.tools.junit.impl.security;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

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


  class ContextKey {

    public ContextKey(String className, String methodName) {
      this.className = className;
      this.methodName = methodName;
    }

    static String createThreadGroupName(String className, String methodName) {
      return className + "-m-" + methodName + "-Threads";
    }

    static ContextKey parseFromThreadGroupName(String threadGroupName) {
      String[] split = threadGroupName.split("-");
      assert split.length == 4;
      assert Objects.equals(split[1], "m");
      assert Objects.equals(split[3], "Threads");
      String methodName = split.length >= 3 ? split[2] : null;
      return new ContextKey(split[0], methodName);
    }

    String className;
    String methodName;

    @Override
    public boolean equals(Object o) {
      if (this == o) return true;
      if (o == null || getClass() != o.getClass()) return false;

      ContextKey that = (ContextKey) o;

      if (className != null ? !className.equals(that.className) : that.className != null)
        return false;
      return methodName != null ? methodName.equals(that.methodName) : that.methodName == null;
    }

    @Override
    public int hashCode() {
      return Objects.hash(className, methodName);
    }

    public String getClassName() {
      return className;
    }

    public String testNameString() {
      return className + "#" + methodName;
    }

    public String getThreadGroupName() {
      return createThreadGroupName(className, methodName);
    }
  }

  class TestCaseSecurityContext implements TestSecurityContext {

    private final ContextKey contextKey;
    private final ThreadGroup threadGroup;
    private Exception failureException;

    public TestCaseSecurityContext(String className, String methodName) {
      this.contextKey = new ContextKey(className, methodName);
      this.threadGroup = new ThreadGroup(contextKey.getThreadGroupName());

    }

    public ThreadGroup getThreadGroup() {
      return threadGroup;
    }

    @Override
    public String getClassName() {
      return contextKey.getClassName();
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
          contextKey.testNameString() +
          ", threadGroup=" + threadGroup +
          ", threadGroupActiveCt=" + threadGroup.activeCount() +
          ", failureException=" + failureException +
          '}';
    }
  }

  class SuiteTestSecurityContext implements TestSecurityContext {

    private final ContextKey contextKey;

    public SuiteTestSecurityContext(String className) {
      contextKey = new ContextKey(className, null);
    }

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
      return contextKey.getClassName();
    }
  }
}
