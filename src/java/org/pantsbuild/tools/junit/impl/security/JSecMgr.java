package org.pantsbuild.tools.junit.impl.security;

import java.io.PrintStream;
import java.security.Permission;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.Callable;
import java.util.logging.Logger;

public class JSecMgr extends SecurityManager {

  private static Logger logger = Logger.getLogger("pants-junit-sec-mgr");

  // these are going to be overridden because multiple tests own a classname, so the lookup needs
  // to be by class then method
  private final Map<String, TestSecurityContext> classNameToSettings = new HashMap<>();
  private final ThreadLocal<TestSecurityContext> settingsRef = new ThreadLocal<>();

  final JSecMgrConfig config;
  private final PrintStream out;

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


  public JSecMgr(JSecMgrConfig config, PrintStream out) {
    super();
    this.config = config;
    this.out = out;
  }

  Throwable securityIssue() {
    TestSecurityContext testSecurityContext = lookupContext();
    if (testSecurityContext == null) {
      return null;
    }
    log("securityIssue", "                                 " + testSecurityContext.getFailures());
    return testSecurityContext.getFailures().get(0);
  }

  void startTest(TestSecurityContext.TestCaseSecurityContext testSecurityContext) {
    //TestSecurityContext andSet = settingsRef.getAndSet(testSecurityContext);
    TestSecurityContext andSet = settingsRef.get();
    settingsRef.set(testSecurityContext);
    classNameToSettings.put(testSecurityContext.getClassName(), testSecurityContext);
    if (andSet != null) {
      // complain
    }
  }

  boolean hasDanglingThreads(String className) {
    TestSecurityContext testSecurityContext = getContextForClassName(className);
    if (testSecurityContext == null) {
      return false;
    }
    return testSecurityContext.getThreadGroup().activeCount() > 0;
  }

  boolean hadSecIssue(String className) {
    TestSecurityContext testSecurityContext = getContextForClassName(className);
    return hadSecIssue(testSecurityContext);
  }

  private TestSecurityContext lookupContext() {
    // hit ref, if that fails
    // check the current thread group
    // else
    // walk the stack to find a matching class.
    TestSecurityContext contextFromRef = settingsRef.get();
    if (contextFromRef != null) {
      log("lookupContext", "found via ref!");
      return contextFromRef;
    }

    String threadGroupName = Thread.currentThread().getThreadGroup().getName();
    String[] split = threadGroupName.split("-");
    String classNameFromThreadGroup = split[0];
    //String methodNameFromThreadGroup = split[2];
    TestSecurityContext contextFromThreadGroup = getContextForClassName(classNameFromThreadGroup);
    if (contextFromThreadGroup != null) {
      log("lookupContext", "found via thread group: " + threadGroupName);
      return contextFromThreadGroup;
    } else {
      log("lookupContext", " not found thread group: " + threadGroupName);
      log("lookupContext", " available " + classNameToSettings.keySet());
    }

    for (Class<?> c : getClassContext()) {
      // this will no longer match.
      TestSecurityContext testSecurityContext = getContextForClassName(c.getName());
      if (testSecurityContext != null) {
        log("lookupContext", "found matching stack element!");
        return testSecurityContext;
      }
    }
    return null;
  }

  private void log(String methodName, String msg) {
    logger.fine("---" + methodName + ":" + msg);
  }

  private boolean hadSecIssue(TestSecurityContext testSecurityContext) {
    if (testSecurityContext == null) {
      return false;
    }

    return testSecurityContext.getFailures().size() > 0;
  }

  private TestSecurityContext getContextForClassName(String className) {
    return classNameToSettings.get(className);
  }

  TestSecurityContext contextFor(String className) {
    return getContextForClassName(className);
  }

  public boolean anyHasDanglingThreads() {
    for (Map.Entry<String, TestSecurityContext> k : classNameToSettings.entrySet()) {
      if (k.getValue().getThreadGroup().activeCount() > 0) {
        return true;
      }
    }
    return false;
  }

  void endTest() {
    settingsRef.remove();
  }

  public void withSettings(TestSecurityContext.TestCaseSecurityContext testSecurityContext, Runnable runnable) {
    startTest(testSecurityContext);
    runnable.run();
    endTest();
  }

  public <V> V withSettings(TestSecurityContext.TestCaseSecurityContext context, Callable<V> callable) throws Exception {
    startTest(context);
    V result = callable.call();
    endTest();
    return result;
  }

  public void interruptDanglingThreads() {
  }


  @Override
  public Object getSecurityContext() {
    return settingsRef.get();
  }

  @Override
  public void checkPermission(Permission perm) {
    if (deferPermission(perm)) {
      super.checkPermission(perm);
    }
  }

  @Override
  public void checkPermission(Permission perm, Object context) {
    super.checkPermission(perm, context);
  }

  private boolean deferPermission(Permission perm) {
    return false;
  }

  @Override
  public ThreadGroup getThreadGroup() {
    TestSecurityContext testSecurityContext = lookupContext();
    if (testSecurityContext != null) {
      return testSecurityContext.getThreadGroup();
    } else {
      return null;
    }
  }

  @Override
  public void checkExit(int status) {
    //out.println("tried a system exit!");
    //System.out.println("tried a system exit! System.out");
    //System.err.println("tried a system exit! on err");
    //if (true) {
    //  throw new RuntimeException("wut");
    //}
    //Thread.currentThread().getThreadGroup()
    if (config.disallowSystemExit()) {
      // TODO improve message so that it points out the line the call happened on more explicitly.
      //
      SecurityException ex;
      TestSecurityContext context = lookupContext();
      if (context != null) {
        ex = new SecurityException("System.exit calls are not allowed. context: " + context);
            /*"\n" +
            "  "+ testSecurityContext.className+ "\n"+
            "  cur thread group: "+ threadGroup+"\n"+
            "    thrd ct: "+threadGroup.activeCount() +"\n"+
            "  testSecurityContext thread group: "+ testSecurityContext.threadGroup+"\n"+
            "    thrd ct: "+ testSecurityContext.threadGroup.activeCount() +"\n"

        );*/
        context.addFailure(ex);
      } else {
        log("checkExit", "Couldn't find a context for disallowed system exit!");
        ex = new SecurityException("System.exit calls are not allowed.");
      }
      // docs say to call super before throwing.
      super.checkExit(status);
      throw ex;
    }
  }


}
