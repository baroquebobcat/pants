package org.pantsbuild.tools.junit.impl.security;

import java.util.Collection;
import java.util.HashMap;
import java.util.Map;

class JunitSecurityLogic {
  // TODO handling of this is pretty messy and will have problems across threads if notifiers are
  // not synchronized.
  private final ThreadLocal<TestSecurityContext> settingsRef = new ThreadLocal<>();
  private final Map<String, TestSecurityContext.SuiteTestSecurityContext> classNameToSuiteContext = new HashMap<>();
  final JSecMgrConfig config;
  JunitSecurityLogic(JSecMgrConfig config) {
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
