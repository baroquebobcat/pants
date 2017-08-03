package org.pantsbuild.tools.junit.impl.security;

import java.util.Collection;
import java.util.HashMap;
import java.util.Map;

// TODO this is a terrible name.
class JunitSecurityContextLookupAndErrorCollection {

  // lifecycle
  // execution contexts:
  //   StaticContext
  //      when the class containing tests is loaded
  //   SuiteContext
  //      while the beforeclass et al are being run -- analogous to classBlock in the block runner
  //   TestContext
  //      while the test case is running
  //
  // thread contexts:

  //    Test class context / might also be suite context
  //       holds threads started in the class/suite context
  //    Test case context
  //       holds threads started in the method/case context
  //    Q should threads started in a static context be considered to exist in the class context?
  //

  // exception handling:
  //   allow tests to swallow Security exceptions
  //   force test failure on Sec exceptions
  // scopes:
  //   test suite
  //   all tests
  //   test case
  //   static eval
  //
  // file:
  //   disallow all
  //   allow only specified files / dirs
  //   allow all
  //
  // network:
  //   disallow all
  //   allow only localhost and loop back
  //   allow only localhost connections, but allow dns resolve to see if address is pointed at
  //              localhost
  //   allow all
  //

  // disallow network access


  // scheme.
  //   sets a thread local with the testSecurityContext
  //   if a thread is created, injects the testSecurityContext into its thread local table when it
  //   is constructed.
  //   not sure if thats possible.
  //   could use this for ThreadGroups

  // java.io.FilePermission
  // , java.net.SocketPermission,
  // java.net.NetPermission,
  // java.security.SecurityPermission,
  // java.lang.RuntimePermission,
  // java.util.PropertyPermission, java.awt.AWTPermission, java.lang.reflect.ReflectPermission,
  // and java.io.SerializablePermission.

  // TODO handling of this is pretty messy and will have problems across threads if notifiers are
  // not synchronized.
  private final ThreadLocal<TestSecurityContext> settingsRef = new ThreadLocal<>();
  private final Map<String, TestSecurityContext.SuiteTestSecurityContext> classNameToSuiteContext = new HashMap<>();
  final JSecMgrConfig config;
  JunitSecurityContextLookupAndErrorCollection(JSecMgrConfig config) {
    this.config = config;
  }

  void removeCurrentThreadSecurityContext() {
    settingsRef.remove();
  }

  void startTest(TestSecurityContext.TestCaseSecurityContext testSecurityContext) {
    TestSecurityContext.SuiteTestSecurityContext suiteContext = classNameToSuiteContext.get(testSecurityContext.getClassName());
    if (suiteContext != null) {
      suiteContext.addChild(testSecurityContext);
    } else {
      TestSecurityContext.SuiteTestSecurityContext value = new TestSecurityContext.SuiteTestSecurityContext(testSecurityContext.getClassName());
      classNameToSuiteContext.put(testSecurityContext.getClassName(), value);
      value.addChild(testSecurityContext);
    }
    getAndSetLocal(testSecurityContext);
  }

  void startTest(TestSecurityContext.ContextKey contextKey) {
    TestSecurityContext.SuiteTestSecurityContext suiteContext = classNameToSuiteContext.get(contextKey.getClassName());
    if (suiteContext == null) {
      suiteContext= new TestSecurityContext.SuiteTestSecurityContext(contextKey.getClassName());
      classNameToSuiteContext.put(contextKey.getClassName(), suiteContext);
    }

    TestSecurityContext.TestCaseSecurityContext testSecurityContext = new TestSecurityContext.TestCaseSecurityContext(contextKey, suiteContext);
    suiteContext.addChild(testSecurityContext);
    getAndSetLocal(testSecurityContext);
  }

  void startSuite(TestSecurityContext.ContextKey contextKey) {
    TestSecurityContext.SuiteTestSecurityContext securityContext = new TestSecurityContext.SuiteTestSecurityContext(contextKey.getClassName());
    getAndSetLocal(securityContext);
    classNameToSuiteContext.put(contextKey.getClassName(), securityContext);
  }

  private void getAndSetLocal(TestSecurityContext testSecurityContext) {
    TestSecurityContext andSet = settingsRef.get();
    settingsRef.set(testSecurityContext);
    if (andSet != null) {
      // complain maybe.
    }
  }

  void endTest() {
    removeCurrentThreadSecurityContext();
  }

  TestSecurityContext getCurrentSecurityContext() {
    return settingsRef.get();
  }

  TestSecurityContext getContextForClassName(String className) {
    return classNameToSuiteContext.get(className);
  }

  boolean anyHasRunningThreads() {
    for (Map.Entry<String, TestSecurityContext.SuiteTestSecurityContext> k : classNameToSuiteContext.entrySet()) {
      if (k.getValue().hasActiveThreads()) {
        return true;
      }
    }
    return false;
  }

  Collection<String> availableClasses() {
    return classNameToSuiteContext.keySet();
  }

  TestSecurityContext getContext(TestSecurityContext.ContextKey contextKey) {
    if (contextKey.getClassName() != null) {
      TestSecurityContext.SuiteTestSecurityContext suiteContext = classNameToSuiteContext.get(contextKey.getClassName());
      if (suiteContext == null) {
        return null;
      }
      if (contextKey.isSuiteKey()) {
        return suiteContext;
      }
      if (suiteContext.hasNoChildren()) {
        return suiteContext;
      }
      return suiteContext.getChild(contextKey.getMethodName());
    }
    return null;
  }

  TestSecurityContext lookupContextByThreadGroup() {
    TestSecurityContext.ContextKey contextKey = TestSecurityContext.ContextKey.parseFromThreadGroupName(Thread.currentThread().getThreadGroup().getName());
    return getContext(contextKey);
  }

  boolean disallowsThreadsFor(TestSecurityContext context) {
    switch (config.getThreadHandling()) {
      case allowAll:
        return false;
      case disallow:
        return true;
      case disallowDanglingTestCaseThreads:
        return true;
      case disallowDanglingTestSuiteThreads:
        return context instanceof TestSecurityContext.SuiteTestSecurityContext;
      default:
        return false;
    }
  }
}
