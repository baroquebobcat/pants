package org.pantsbuild.tools.junit.impl;

import java.io.PrintStream;
import java.security.Permission;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.Callable;

public class JSecMgr extends SecurityManager {

  // these are going to be overridden because multiple tests own a classname, so the lookup needs
  // to be by class then method
  private final Map<String, TestSecurityContext> classNameToSettings = new HashMap<>();
  private final ThreadLocal<TestSecurityContext> settingsRef = new ThreadLocal<>();

  private final JSecMgrConfig config;
  private final PrintStream out;

  public boolean hadSecIssue() {
    TestSecurityContext testSecurityContext = lookupContext();
    return hadSecIssue(testSecurityContext);
  }

  public Throwable securityIssue() {
    TestSecurityContext testSecurityContext = lookupContext();
    if (testSecurityContext == null) {
      return null;
    }
    System.out.println("                                 "+ testSecurityContext.getFailures());
    return testSecurityContext.getFailures().get(0);
  }

  public void startTest(TestSecurityContext testSecurityContext) {
    //TestSecurityContext andSet = settingsRef.getAndSet(testSecurityContext);
    TestSecurityContext andSet = settingsRef.get();
    settingsRef.set(testSecurityContext);
    classNameToSettings.put(testSecurityContext.className, testSecurityContext);
    if (andSet != null) {
      // complain
    }
  }

  public boolean hasDanglingThreads(String className) {
    TestSecurityContext testSecurityContext = getContextsForClassName(className);
    if (testSecurityContext == null) {
      return false;
    }
    return testSecurityContext.threadGroup.activeCount() > 0;
  }

  public boolean hadSecIssue(String className) {
    TestSecurityContext testSecurityContext = getContextsForClassName(className);
    return hadSecIssue(testSecurityContext);
  }

  private TestSecurityContext lookupContext() {
    // hit ref, if that fails
    // check the current thread group
    // else
    // walk the stack to find a matching class.
    TestSecurityContext testSecurityContextFromRef = settingsRef.get();
    if (testSecurityContextFromRef != null) {
      log("lookupContext", "found via ref!");
      return testSecurityContextFromRef;
    }

    String threadGroupName = Thread.currentThread().getThreadGroup().getName();
    String classNameFromThreadGroupName = threadGroupName.split("-")[0];
    TestSecurityContext testSecurityContextFromThreadGroup = getContextsForClassName(
        classNameFromThreadGroupName );
    if (testSecurityContextFromThreadGroup != null) {
      log("lookupContext", "found via thread group: "+threadGroupName);
      return testSecurityContextFromThreadGroup;
    } else {
      log("lookupContext", " not found thread group: " + threadGroupName);
      log("lookupContext", " available "+classNameToSettings.keySet());
    }

    for (Class<?> c :getClassContext()) {
      // this will no longer match.
      TestSecurityContext testSecurityContext = getContextsForClassName(c.getName());
      if (testSecurityContext != null) {
        log("lookupContext", "found matching stack element!");
        return testSecurityContext;
      }
    }
    return null;
  }

  private void log(String methodName, String msg) {
    System.out.println("---" + methodName + ":" + msg);
  }

  private boolean hadSecIssue(TestSecurityContext testSecurityContext) {
    if (testSecurityContext == null) {
      return false;
    }

    return testSecurityContext.getFailures().size() > 0;
  }

  private TestSecurityContext getContextsForClassName(String className) {
    return classNameToSettings.get(className);
  }

  public TestSecurityContext contextFor(String className) {
    return getContextsForClassName(className);
  }

  public boolean anyHasDanglingThreads() {
    for (Map.Entry<String, TestSecurityContext> k : classNameToSettings.entrySet()) {
      if (k.getValue().threadGroup.activeCount() > 0) {
        return true;
      }
    }
    return false;
  }

  static class JSecMgrConfig {

    public final boolean useThreadGroup;
    public final boolean allowExit;

    JSecMgrConfig(boolean useThreadGroup, boolean allowExit) {
      this.useThreadGroup = useThreadGroup;
      this.allowExit = allowExit;
    }
  }

  public static class TestSecurityContext {

    private String className;
    private ThreadGroup threadGroup;
    private final String methodName;
    private Exception failureException;


    public TestSecurityContext(String className, String methodName) {
      this.className = className;
      this.threadGroup = new ThreadGroup(className + "-m-" + methodName + "-Threads");
      this.methodName = methodName;
    }

    ThreadGroup getThreadGroup() {
      return threadGroup;
    }

    public void addFailure(Exception ex) {
      failureException = ex;
    }

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
      return "TestSecurityContext{" +
          "className='" + className + '\'' +
          ", threadGroup=" + threadGroup +
          ", threadGroupActiveCt=" + threadGroup.activeCount() +
          ", failureException=" + failureException +
          '}';
    }
  }

  JSecMgr(JSecMgrConfig config, PrintStream out) {
    this.config = config;
    this.out = out;
  }

  public void endTest() {
    settingsRef.remove();
  }

  // scheme.
  //   sets a thread local with the testSecurityContext
  //   if a thread is created, injects the testSecurityContext into its thread local table when it is
  //   constructed.
  //   not sure if thats possible.
  //   could use this for ThreadGroups
  public void withSettings(TestSecurityContext testSecurityContext, Runnable runnable) {
    startTest(testSecurityContext);
    runnable.run();
    endTest();
  }

  public <V> V withSettings(TestSecurityContext testSecurityContext, Callable<V> callable) throws Exception {
    startTest(testSecurityContext);
    V result = callable.call();
    endTest();
    return result;
  }

  public Object getSecurityContext() {
    return settingsRef.get();
  }

  public void checkPermission(Permission perm) {
    if (deferPermission(perm)) {
      super.checkPermission(perm);
    }
  }

  public void checkPermission(Permission perm, Object context) {
    super.checkPermission(perm, context);
  }

  private boolean deferPermission(Permission perm) {
    return false;
  }


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
  // System.exit
  //   disallow
  //   allow
  //
  // Threads
  //   disallow creation
  //   fail if threads live beyond test case
  //   fail if threads live beyond test suite
  //   allow all
  // disallow network access


  // java.io.FilePermission
  // , java.net.SocketPermission,
  // java.net.NetPermission,
  // java.security.SecurityPermission,
  // java.lang.RuntimePermission,
  // java.util.PropertyPermission, java.awt.AWTPermission, java.lang.reflect.ReflectPermission,
  // and java.io.SerializablePermission.

  public ThreadGroup getThreadGroup() {
    TestSecurityContext testSecurityContext = lookupContext();
    if (testSecurityContext != null) {
      return testSecurityContext.getThreadGroup();
    } else {
      return null;
    }
  }

  public void checkExit(int status) {
    out.println("tried a system exit!");
    //System.out.println("tried a system exit! System.out");
    //System.err.println("tried a system exit! on err");
    //if (true) {
    //  throw new RuntimeException("wut");
    //}
    //Thread.currentThread().getThreadGroup()
    if (!config.allowExit) {
      // TODO improve message so that it points out the line the call happened on more explicitly.
      //
      SecurityException ex;
      TestSecurityContext testSecurityContext = lookupContext();
      if (testSecurityContext != null) {
        ThreadGroup threadGroup = Thread.currentThread().getThreadGroup();
        ex = new SecurityException("System.exit calls are not allowed.\n" +
            "  "+ testSecurityContext.className+ "\n"+
            "  cur thread group: "+ threadGroup+"\n"+
            "    thrd ct: "+threadGroup.activeCount() +"\n"+
            "  testSecurityContext thread group: "+ testSecurityContext.threadGroup+"\n"+
            "    thrd ct: "+ testSecurityContext.threadGroup.activeCount() +"\n"

        );
        testSecurityContext.addFailure(ex);
      } else {
        ex = new SecurityException("System.exit calls are not allowed.");
        // TODO maybe do something here
      }
      // docs say to call super before throwing.
      super.checkExit(status);
      throw ex;
    }
  }
}
