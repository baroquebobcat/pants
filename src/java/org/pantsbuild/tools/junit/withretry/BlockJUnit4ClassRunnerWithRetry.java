// Copyright 2015 Pants project contributors (see CONTRIBUTORS.md).
// Licensed under the Apache License, Version 2.0 (see LICENSE).

package org.pantsbuild.tools.junit.withretry;

import java.io.PrintStream;
import java.lang.reflect.Method;
import java.util.concurrent.Callable;

import org.junit.runner.notification.RunNotifier;
import org.junit.runners.BlockJUnit4ClassRunner;
import org.junit.runners.model.FrameworkMethod;
import org.junit.runners.model.InitializationError;
import org.junit.runners.model.Statement;
import org.pantsbuild.tools.junit.impl.security.JSecMgr;

/**
 * A subclass of BlockJUnit4ClassRunner that supports retrying failing tests, up to the
 * specified number of attempts. This is useful if some tests are known or suspected
 * to be flaky.
 */
public class BlockJUnit4ClassRunnerWithRetry extends BlockJUnit4ClassRunner {

  private final int numRetries;
  private final PrintStream err;

  public BlockJUnit4ClassRunnerWithRetry(Class<?> klass, int numRetries, PrintStream err)
      throws InitializationError {
    super(klass);
    this.numRetries = numRetries;
    this.err = err;
  }

  protected Statement createStatement(FrameworkMethod method) {
    return super.methodBlock(method);
  }

  protected Statement classBlock(final RunNotifier notifier) {
    return super.classBlock(notifier);
  }

  @Override
  protected Statement methodBlock(FrameworkMethod method) {
    return new InvokeWithRetry(method);
  }

  private class WithSecManagerStuff extends Statement {
    private final Statement inner;

    WithSecManagerStuff(Statement inner) {
      this.inner = inner;
    }

    @Override
    public void evaluate() throws Throwable {
      ((JSecMgr)System.getSecurityManager()).withSettings(
          new JSecMgr.TestCaseSecurityContext("something", "somemethod"), new Callable<Void>() {
        @Override
        public Void call() {
          try {
            inner.evaluate();
          } catch (Throwable throwable) {
            throwable.printStackTrace();
            // AAAAAAAaaargh
            throw new RuntimeException(throwable);
          }
          return null;
        }
      });
    }
  }

  private class InvokeWithRetry extends Statement {

    private final FrameworkMethod method;

    InvokeWithRetry(FrameworkMethod method) {
      this.method = method;
    }

    @Override
    public void evaluate() throws Throwable {
      // could inject the sec mgr here, since this wraps the full thing.
      Throwable error = null;
      for (int i = 0; i <= numRetries; i++) {
        try {
          // This re-creates the Test object every time (including retries), to make everything
          // as close as possible to clean manual re-invocation of the failed test. It also
          // ensures that all the things encapsulated by the top-level Statement, e.g. setup/
          // teardown, checking for expected exceptions, etc., are redone every time.
          createStatement(method).evaluate();
          // The test succeeded. However, if it has been retried, it's flaky.
          if (i > 0) {
            Method m = method.getMethod();
            String testName = m.getName() + '(' + m.getDeclaringClass().getName() + ')';
            err.println("Test " + testName + " is FLAKY; passed after " + (i + 1) + " attempts");
          }
          return;
        // We want implement generic retry logic here with exception capturing as a key part.
        // SUPPRESS CHECKSTYLE RegexpSinglelineJava
        } catch (Throwable t) {
          // Test failed - save the very first thrown exception. However, if we caught an
          // Error other than AssertionError, exit immediately. It probably doesn't make
          // sense to retry a test after an OOM or LinkageError.
          if (t instanceof Exception || t instanceof AssertionError) {
            if (error == null) {
              error = t;
            }
          } else {
            throw t;
          }
        }
      }
      throw error;
    }
  }

}
