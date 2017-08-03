package org.pantsbuild.tools.junit.impl.security;

import java.util.concurrent.Callable;

import org.junit.runner.Description;
import org.junit.runners.model.Statement;

public class WrapStatementWithSecurityManager extends Statement {
  private final JunitSecViolationReportingManager junitSecViolationReportingManager;
  private final TestSecurityContext.ContextKey contextKey;
  private final Statement inner;

  public WrapStatementWithSecurityManager(JunitSecViolationReportingManager junitSecViolationReportingManager, TestSecurityContext.ContextKey contextKey, Statement inner) {
    this.junitSecViolationReportingManager = junitSecViolationReportingManager;
    this.contextKey = contextKey;
    this.inner = inner;
  }

  @Override
  public void evaluate() throws Throwable {
    JunitSecViolationReportingManager junitSecViolationReportingManager = (JunitSecViolationReportingManager) System.getSecurityManager();
    if (junitSecViolationReportingManager == null) {
      inner.evaluate();
      return;
    }

    junitSecViolationReportingManager.withSettings(
        contextKey,
        new Callable<Void>() {
      @Override
      public Void call() {
        try {
          inner.evaluate();
        } catch (Throwable throwable) {
          // The runtime exception here is unwrapped and rethrown by withSettings
          // TODO come up with a better protocol
          throw new RuntimeException(throwable);
        }
        return null;
      }
    });
  }

  public static Statement wrappedStatement(Description description, Statement statement) {
    JunitSecViolationReportingManager junitSecViolationReportingManager = (JunitSecViolationReportingManager) System.getSecurityManager();
    if (junitSecViolationReportingManager == null) {
      return statement;
    }

    return new WrapStatementWithSecurityManager(
        junitSecViolationReportingManager,
        new TestSecurityContext.ContextKey(description.getClassName()),
        statement);
  }
}
