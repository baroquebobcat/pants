package org.pantsbuild.tools.junit.impl.security;

import java.io.FileDescriptor;
import java.security.AccessController;
import java.security.Permission;
import java.security.PrivilegedActionException;
import java.security.PrivilegedExceptionAction;
import java.util.concurrent.Callable;
import java.util.logging.Logger;

import static org.pantsbuild.tools.junit.impl.security.TestSecurityContext.*;

public class JunitSecViolationReportingManager extends SecurityManager {

  private static Logger logger = Logger.getLogger("pants-junit-sec-mgr");

  private final JunitSecurityContextLookupAndErrorCollection contextLookupAndErrorCollection;

  public JunitSecViolationReportingManager(JSecMgrConfig config) {
    super();
    this.contextLookupAndErrorCollection = new JunitSecurityContextLookupAndErrorCollection(config);
  }

  public static <T> T maybeWithSecurityManagerContext(final String className, final Callable<T> callable) throws Exception {
    SecurityManager securityManager = System.getSecurityManager();
    // skip if there is no security manager
    if (securityManager == null) {
      return callable.call();
    }
    final JunitSecViolationReportingManager jsecViolationReportingManager = (JunitSecViolationReportingManager) securityManager;
    try {
      // doPrivileged here allows us to wrap all
      return AccessController.doPrivileged(
          new PrivilegedExceptionAction<T>() {
            @Override
            public T run() throws Exception {
              try {
                return jsecViolationReportingManager.withSettings(
                    new ContextKey(className),
                    callable);
              } catch (Exception e) {
                throw e;
              } catch (Throwable t) {
                throw new RuntimeException(t);
              }
            }
          },
          AccessController.getContext()
      );
    } catch (PrivilegedActionException e) {
      throw e.getException();
    }
  }

  public boolean disallowsThreadsFor(TestSecurityContext context) {
    return contextLookupAndErrorCollection.disallowsThreadsFor(context);
  }

  public boolean perClassThreadHandling() {
    return contextLookupAndErrorCollection.config.getThreadHandling() == JSecMgrConfig.ThreadHandling.disallowDanglingTestSuiteThreads;
  }

  void startTest(TestCaseSecurityContext testSecurityContext) {
    contextLookupAndErrorCollection.startTest(testSecurityContext);
  }

  void startTest(ContextKey testSecurityContext) {
    contextLookupAndErrorCollection.startTest(testSecurityContext);
  }

  void startSuite(String className) {
    contextLookupAndErrorCollection.startSuite(new ContextKey(className));
  }

  private TestSecurityContext lookupContext() {
    TestSecurityContext contextFromRef = contextLookupAndErrorCollection.getCurrentSecurityContext();
    if (contextFromRef != null) {
      log("lookupContext", "found via ref!");
      return contextFromRef;
    }

    TestSecurityContext contextFromThreadGroup = contextLookupAndErrorCollection.lookupContextByThreadGroup();
    if (contextFromThreadGroup != null) {
      log("lookupContext", "found via thread group");
      return contextFromThreadGroup;
    } else {
      log("lookupContext", " not found thread group: " + Thread.currentThread().getThreadGroup().getName());
      log("lookupContext", " available " + contextLookupAndErrorCollection.availableClasses());
    }

    Class[] classContext = getClassContext();
    for (Class<?> c : classContext) {
      // this will no longer match.
      TestSecurityContext testSecurityContext = contextLookupAndErrorCollection.getContextForClassName(c.getName());
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
    return contextLookupAndErrorCollection.getContextForClassName(className);
  }

  TestSecurityContext contextFor(String className, String methodName) {
    return contextLookupAndErrorCollection.getContext(new ContextKey(className, methodName));
  }

  public boolean anyHasDanglingThreads() {
    return contextLookupAndErrorCollection.anyHasRunningThreads();
  }

  void endTest() {
    contextLookupAndErrorCollection.removeCurrentThreadSecurityContext();
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
    return contextLookupAndErrorCollection.getCurrentSecurityContext();
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
    return contextLookupAndErrorCollection.config.disallowSystemExit();
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
