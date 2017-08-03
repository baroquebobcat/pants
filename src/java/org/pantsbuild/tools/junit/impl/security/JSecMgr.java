package org.pantsbuild.tools.junit.impl.security;

import java.io.FileDescriptor;
import java.io.PrintStream;
import java.security.Permission;
import java.util.Collection;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.Callable;
import java.util.logging.Logger;

import static org.pantsbuild.tools.junit.impl.security.TestSecurityContext.*;

public class JSecMgr extends SecurityManager {

  private static Logger logger = Logger.getLogger("pants-junit-sec-mgr");

  // these are going to be overridden because multiple tests own a classname, so the lookup needs
  // to be by class then method
  private final SecurityLogic securityLogic;

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
    this.securityLogic = new SecurityLogic(config);
    this.out = out;
  }

  public boolean disallowsThreadsFor(TestSecurityContext context) {
    return securityLogic.disallowsThreadsFor(context);
  }

  public boolean perClassThreadHandling() {
    return securityLogic.config.getThreadHandling() == JSecMgrConfig.ThreadHandling.disallowDanglingTestSuiteThreads;
  }

  static class SecurityLogic {
    // TODO handling of this is pretty messy and will have problems across threads if notifiers are
    // not synchronized.
    private final ThreadLocal<TestSecurityContext> settingsRef = new ThreadLocal<>();
    private final Map<String, SuiteTestSecurityContext> classNameToSuiteContext = new HashMap<>();
    final JSecMgrConfig config;
    SecurityLogic(JSecMgrConfig config) {
      this.config = config;
    }

    public TestSecurityContext getCurrentSecurityContext() {
      return settingsRef.get();
    }

    public void removeCurrentThreadSecurityContext() {
      settingsRef.remove();
    }

    public void startTest(TestCaseSecurityContext testSecurityContext) {
      SuiteTestSecurityContext suiteContext = classNameToSuiteContext.get(testSecurityContext.getClassName());
      if (suiteContext != null) {
        suiteContext.addChild(testSecurityContext);
      } else {
        SuiteTestSecurityContext value = new SuiteTestSecurityContext(testSecurityContext.getClassName());
        classNameToSuiteContext.put(testSecurityContext.getClassName(), value);
        value.addChild(testSecurityContext);
      }
      getAndSetLocal(testSecurityContext);
    }

    public void startTest(ContextKey contextKey) {
      SuiteTestSecurityContext suiteContext = classNameToSuiteContext.get(contextKey.getClassName());
      if (suiteContext == null) {
        suiteContext= new SuiteTestSecurityContext(contextKey.getClassName());
        classNameToSuiteContext.put(contextKey.getClassName(), suiteContext);
      }

      TestCaseSecurityContext testSecurityContext = new TestCaseSecurityContext(contextKey, suiteContext);
      suiteContext.addChild(testSecurityContext);
      getAndSetLocal(testSecurityContext);
    }

    public void getAndSetLocal(TestSecurityContext testSecurityContext) {
      TestSecurityContext andSet = settingsRef.get();
      settingsRef.set(testSecurityContext);
      if (andSet != null) {
        // complain maybe.
      }
    }

    public void startSuite(ContextKey contextKey) {
      SuiteTestSecurityContext securityContext = new SuiteTestSecurityContext(contextKey.getClassName());
      getAndSetLocal(securityContext);
      classNameToSuiteContext.put(contextKey.getClassName(), securityContext);
    }

    public TestSecurityContext getContextForClassName(String className) {
      return classNameToSuiteContext.get(className);
    }

    public boolean anyHasRunningThreads() {
      for (Map.Entry<String, SuiteTestSecurityContext> k : classNameToSuiteContext.entrySet()) {
        if (k.getValue().hasActiveThreads()) {
          return true;
        }
      }
      return false;
    }

    public Collection<String> availableClasses() {
      return classNameToSuiteContext.keySet();
    }

    public boolean disallowDanglingThread() {
      return config.disallowDanglingThread();
    }

    public void endTest() {
      removeCurrentThreadSecurityContext();
    }

    public TestSecurityContext getContext(ContextKey contextKey) {
      if (contextKey.getClassName() != null) {
        SuiteTestSecurityContext suiteContext = classNameToSuiteContext.get(contextKey.getClassName());
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

    public TestSecurityContext lookupContextByThreadGroup() {
      ContextKey contextKey = ContextKey.parseFromThreadGroupName(Thread.currentThread().getThreadGroup().getName());
      return getContext(contextKey);
    }

    public boolean disallowsThreadsFor(TestSecurityContext context) {
      switch (config.getThreadHandling()) {
        case allowAll:
          return false;
        case disallow:
          return true;
        case disallowDanglingTestCaseThreads:
          return true;
        case disallowDanglingTestSuiteThreads:
          return context instanceof SuiteTestSecurityContext;
        default:
          return false;
      }

    }
  }

  void startTest(TestCaseSecurityContext testSecurityContext) {
    securityLogic.startTest(testSecurityContext);
  }

  void startTest(ContextKey testSecurityContext) {
    securityLogic.startTest(testSecurityContext);
  }

  void startSuite(String className) {
    securityLogic.startSuite(new ContextKey(className));
  }

  private TestSecurityContext lookupContext() {
    // hit ref, if that fails
    // check the current thread group
    // else
    // walk the stack to find a matching class.
    TestSecurityContext contextFromRef = securityLogic.getCurrentSecurityContext();
    if (contextFromRef != null) {
      log("lookupContext", "found via ref!");
      return contextFromRef;
    }

    TestSecurityContext contextFromThreadGroup = securityLogic.lookupContextByThreadGroup();
    if (contextFromThreadGroup != null) {
      log("lookupContext", "found via thread group");
      return contextFromThreadGroup;
    } else {
      log("lookupContext", " not found thread group: " + Thread.currentThread().getThreadGroup().getName());
      log("lookupContext", " available " + securityLogic.availableClasses());
    }

    Class[] classContext = getClassContext();
    for (Class<?> c : classContext) {
      // this will no longer match.
      TestSecurityContext testSecurityContext = securityLogic.getContextForClassName(c.getName());
      if (testSecurityContext != null) {
        log("lookupContext", "found matching stack element!");
        return testSecurityContext;
      }
    }
    return null;
  }

  private static void log(String methodName, String msg) {
    logger.fine("---" + methodName + ":" + msg);
  }

  TestSecurityContext contextFor(String className) {
    return securityLogic.getContextForClassName(className);
  }

  TestSecurityContext contextFor(String className, String methodName) {
    return securityLogic.getContext(new ContextKey(className, methodName));
  }

  public boolean anyHasDanglingThreads() {
    return securityLogic.anyHasRunningThreads();
  }

  void endTest() {
    securityLogic.removeCurrentThreadSecurityContext();
  }

  public void withSettings(ContextKey contextKey, Runnable runnable) {
    startTest(contextKey);
    runnable.run();
    endTest();
  }

  public <V> V withSettings(ContextKey context, Callable<V> callable) throws Throwable {
    if (context.isSuiteKey()) {
      startSuite(context.getClassName());
    } else {
      startTest(context);
    }
    try {
      return callable.call();
    } catch (RuntimeException e) {
      throw e.getCause();
    }finally {
      endTest();

    }
  }

  public void interruptDanglingThreads() {
  }


  @Override
  public Object getSecurityContext() {
    return securityLogic.getCurrentSecurityContext();
  }

  @Override
  public void checkPermission(Permission perm) {
    if (deferPermission(perm)) {
      super.checkPermission(perm);
    }
    // TODO disallow setSecurityManager if we are in a test context
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
    if (disallowSystemExit()) {
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

  public boolean disallowSystemExit() {
    return securityLogic.config.disallowSystemExit();
  }

  @Override
  public void checkConnect(final String host, final int port) {

  }

  @Override
  public void checkRead(FileDescriptor fd) {

  }

  @Override
  public void checkRead(String filename, Object context) {

  }

  @Override
  public void checkRead(String filename) {

  }

  @Override
  public void checkWrite(FileDescriptor fd) {

  }

  @Override
  public void checkWrite(String filename) {

  }

}
