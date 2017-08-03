package org.pantsbuild.tools.junit.impl.security;

import java.io.FileDescriptor;
import java.io.PrintStream;
import java.security.Permission;
import java.util.concurrent.Callable;
import java.util.logging.Logger;

import static org.pantsbuild.tools.junit.impl.security.TestSecurityContext.*;

public class JunitSecViolationReportingManager extends SecurityManager {

  private static Logger logger = Logger.getLogger("pants-junit-sec-mgr");

  private final JunitSecurityContextLookupAndErrorCollection securityLogic;

  private final PrintStream out;

  public JunitSecViolationReportingManager(JSecMgrConfig config, PrintStream out) {
    super();
    this.securityLogic = new JunitSecurityContextLookupAndErrorCollection(config);
    this.out = out;
  }

  public boolean disallowsThreadsFor(TestSecurityContext context) {
    return securityLogic.disallowsThreadsFor(context);
  }

  public boolean perClassThreadHandling() {
    return securityLogic.config.getThreadHandling() == JSecMgrConfig.ThreadHandling.disallowDanglingTestSuiteThreads;
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
