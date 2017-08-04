package org.pantsbuild.tools.junit.impl.security;

import java.util.Collection;
import java.util.HashMap;
import java.util.Map;
import java.util.logging.Logger;

// TODO this is a terrible name.
class JunitSecurityContextLookupAndErrorCollection {

  // lifecycle
  // execution contexts:
  //   StaticContext
  //      when the class containing tests is loaded
  //   SuiteContext
  //      while the beforeclass et al are being run -- analogous to classBlock in the block runner
  //      But, classes may not always be 1:1 with suites
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
  // Flag possibilities
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
  // scheme.
  //   sets a thread local with the testSecurityContext
  //   if a thread is created, injects the testSecurityContext into its thread local table when it
  //   is constructed.
  //   not sure if thats possible.
  //   could use this for ThreadGroups

  // Permissions to write checks for.
  // java.io.FilePermission
  // , java.net.SocketPermission,
  // java.net.NetPermission,
  // java.security.SecurityPermission,
  // java.lang.RuntimePermission,
  // java.util.PropertyPermission, java.awt.AWTPermission, java.lang.reflect.ReflectPermission,
  // and java.io.SerializablePermission.

  // TODO handling of writing SuiteContexts and failures is pretty messy and will have problems
  // across threads if notifiers are not synchronized.
  private final ThreadLocal<TestSecurityContext> settingsRef = new ThreadLocal<>();
  private final Map<String, TestSecurityContext.SuiteTestSecurityContext> classNameToSuiteContext = new HashMap<>();
  private static final Logger logger = Logger.getLogger("junit-security-context");
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
      suiteContext = new TestSecurityContext.SuiteTestSecurityContext(contextKey.getClassName());
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

  private Collection<String> availableClasses() {
    return classNameToSuiteContext.keySet();
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

  TestSecurityContext lookupWithoutExaminingClassContext() {
    TestSecurityContext cheaperContext = null;
    TestSecurityContext contextFromRef = getCurrentSecurityContext();
    if (contextFromRef != null) {
      logger.fine("lookupContext: found via ref!");
      cheaperContext = contextFromRef;
    }

    if (cheaperContext == null) {
      TestSecurityContext contextFromThreadGroup = lookupContextByThreadGroup();
      if (contextFromThreadGroup != null) {
        logger.fine("lookupContext: found via thread group");
        cheaperContext = contextFromThreadGroup;
      } else {
        logger.fine("lookupContext: not found thread group: " + Thread.currentThread().getThreadGroup().getName());
        logger.fine("lookupContext: available " + availableClasses());
      }
    }
    return cheaperContext;
  }


  TestSecurityContext lookupContextFromClassContext(Class[] classContext) {
    for (Class<?> c : classContext) {
      // Will only find the classes context and not the test cases, but it's better than not finding
      // any
      TestSecurityContext testSecurityContext = getContextForClassName(c.getName());
      if (testSecurityContext != null) {
        logger.fine("lookupContext: found matching stack element!");
        return testSecurityContext;
      }
    }
    return null;
  }
}
