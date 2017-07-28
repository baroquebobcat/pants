package org.pantsbuild.tools.junit.impl.security;

import java.util.concurrent.CountDownLatch;

import static org.hamcrest.CoreMatchers.*;

import org.junit.Test;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.*;
import static org.junit.Assert.fail;
import static org.pantsbuild.tools.junit.impl.security.JSecMgrConfig.*;
import static org.pantsbuild.tools.junit.impl.security.TestSecurityContext.*;

public class SecurityLogicTest {

  CountDownLatch latch = new CountDownLatch(1);
  static class AssertableThread extends Thread {
    Throwable thrown;

    public AssertableThread(ThreadGroup threadGroup, Runnable runnable) {
      super(threadGroup, runnable);
      setUncaughtExceptionHandler(new UncaughtExceptionHandler() {
        @Override
        public void uncaughtException(Thread t, Throwable e) {
          thrown = e;
        }
      });
    }

    public void joinOrRaise() throws Throwable {
      join();
      if (thrown!= null) {
        throw thrown;
      }
    }
  }

  @Test
  public void complainIfNoSuite() {
    JSecMgrConfig config = new JSecMgrConfig(
        SystemExitHandling.disallow,
        ThreadHandling.allowAll);
    JSecMgr.SecurityLogic securityLogic = new JSecMgr.SecurityLogic(config);

    ContextKey testKey = new ContextKey("org.foo.Foo", "test");
    try {
      securityLogic.startTest(testKey);
      fail("Expected starting a test without a suite first to fail.");
    } catch (Exception e) {
      // pass
    }
  }

  @Test
  public void suiteThenTest() throws InterruptedException {
    JSecMgrConfig config = new JSecMgrConfig(
        SystemExitHandling.disallow,
        ThreadHandling.allowAll);
    JSecMgr.SecurityLogic securityLogic = new JSecMgr.SecurityLogic(config);

    ContextKey suiteKey = new ContextKey("org.foo.Foo");
    securityLogic.startSuite(suiteKey);
    TestSecurityContext suiteContext = securityLogic.getContext(suiteKey);

    ContextKey testKey = new ContextKey("org.foo.Foo", "test");
    securityLogic.startTest(testKey);

    TestSecurityContext testContext = securityLogic.getContext(testKey);

    assertFalse(securityLogic.anyHasRunningThreads());
    assertFalse(suiteContext.hasActiveThreads());

    runThreadAwaitingLatch(testContext);

    assertTrue(securityLogic.anyHasRunningThreads());
    assertTrue(suiteContext.hasActiveThreads());
    assertTrue(testContext.hasActiveThreads());

    latch.countDown();
    Thread.sleep(1);

    assertFalse(securityLogic.anyHasRunningThreads());
    assertFalse(suiteContext.hasActiveThreads());
    assertFalse(testContext.hasActiveThreads());

    securityLogic.endTest();
  }

  @Test
  public void looksUpContextCorrectlyFromThreadGroup() throws Throwable {
    JSecMgrConfig config = new JSecMgrConfig(
        SystemExitHandling.disallow,
        ThreadHandling.allowAll);
    final JSecMgr.SecurityLogic securityLogic = new JSecMgr.SecurityLogic(config);

    ContextKey suiteKey = new ContextKey("org.foo.Foo");
    securityLogic.startSuite(suiteKey);
    final TestSecurityContext suiteContext = securityLogic.getContext(suiteKey);

    ContextKey testKey = new ContextKey("org.foo.Foo", "test");
    securityLogic.startTest(testKey);

    final TestSecurityContext testContext = securityLogic.getContext(testKey);

    assertFalse(securityLogic.anyHasRunningThreads());
    assertFalse(suiteContext.hasActiveThreads());

    AssertableThread thread = new AssertableThread(testContext.getThreadGroup(), new Runnable() {
      @Override
      public void run() {
        assertThat(securityLogic.lookupContextByThreadGroup(), is(testContext));
      }
    });
    thread.start();
    thread.joinOrRaise();


    thread = new AssertableThread(suiteContext.getThreadGroup(), new Runnable() {
      @Override
      public void run() {
        assertThat(Thread.currentThread().getThreadGroup().getName(), containsString("-m-null-Threads"));
        assertThat(securityLogic.lookupContextByThreadGroup(), is(suiteContext));
      }
    });
    thread.start();
    thread.joinOrRaise();
  }

  @Test
  public void innerAndOuterThreads() throws InterruptedException {

    JSecMgrConfig config = new JSecMgrConfig(
        SystemExitHandling.disallow,
        ThreadHandling.allowAll);
    JSecMgr.SecurityLogic securityLogic = new JSecMgr.SecurityLogic(config);

    ContextKey suiteKey = new ContextKey("org.foo.Foo");
    securityLogic.startSuite(suiteKey);
    TestSecurityContext suiteContext = securityLogic.getContext(suiteKey);

    ContextKey testKey = new ContextKey("org.foo.Foo", "test");
    securityLogic.startTest(testKey);

    TestSecurityContext testContext = securityLogic.getContext(testKey);

    assertFalse(securityLogic.anyHasRunningThreads());
    assertFalse(suiteContext.hasActiveThreads());

    runThreadAwaitingLatch(suiteContext);

    assertTrue(securityLogic.anyHasRunningThreads());
    assertTrue("suite "+suiteContext, suiteContext.hasActiveThreads());
    assertFalse("test "+testContext, testContext.hasActiveThreads());


    runThreadAwaitingLatch(testContext);

    assertTrue(securityLogic.anyHasRunningThreads());
    assertTrue(suiteContext.hasActiveThreads());
    assertTrue(testContext.hasActiveThreads());

    latch.countDown();
    Thread.sleep(1);

    assertFalse(securityLogic.anyHasRunningThreads());
    assertFalse(suiteContext.hasActiveThreads());
    assertFalse(testContext.hasActiveThreads());

    securityLogic.endTest();
  }

  public void runThreadAwaitingLatch(TestSecurityContext testContext) {
    Thread thread = new Thread(testContext.getThreadGroup(), new Runnable() {
      @Override
      public void run() {
        try {
          latch.await();
        } catch (InterruptedException e) {
          e.printStackTrace();
        }
      }
    });
    thread.start();
  }
}
