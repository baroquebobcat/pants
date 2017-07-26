package org.pantsbuild.tools.junit.impl.security;

public class JSecMgrConfig {

  private final SystemExitHandling systemExitHandling;
  private final ThreadHandling threadHandling;

  public JSecMgrConfig(SystemExitHandling systemExitHandling, ThreadHandling threadHandling) {
    this.systemExitHandling = systemExitHandling;
    this.threadHandling = threadHandling;
  }

  boolean disallowSystemExit() {
    return systemExitHandling == SystemExitHandling.disallow;
  }

  boolean disallowDanglingThread() {
    // TODO handle other thread handling models.
    return threadHandling != ThreadHandling.allowAll;
  }

  public enum SystemExitHandling {
    // allow tests to call system exit. Not sure why you'd want that, but ...
    allow,
    disallow
  }

  public enum ThreadHandling {
    // Allow threads, and allow them to live indefinitely.
    allowAll,
    // Do not allow threads to be started via tests.
    disallow,

    // disallow suites starting threads, but allow test cases to start them as long as they are
    // killed before the end of the test case.
    disallowDanglingTestCaseThreads,

    // allow suites or test cases to start threads,
    // but ensure they are killed at the end of the suite.
    disallowDanglingTestSuiteThreads,

    // Needs a better name, could be same as dangling suite mode.
    // threads started in a context, case or suite can live as long as the context does, but it's an
    // error if they live past it.
    nestedButDanglingDisallowed

    // warn on threads that continue to live
  }
}
